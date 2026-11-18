"""Local CLI filesystem and stdout boundaries; never write into an input."""
import io
import os
from pathlib import Path
import stat
import sys
import tempfile
from .schema import InputError


class OutputError(OSError):
    """The verdict stream is unsafe/unavailable; diagnostics go to stderr only."""


def aliases(a, b):
    if a.resolve() == b.resolve():
        return True
    return a.exists() and b.exists() and os.path.samefile(a, b)


def protect_stdout(paths):
    try:
        info = os.fstat(sys.stdout.fileno())
    except (AttributeError, io.UnsupportedOperation):
        return  # A caller-supplied in-memory stream cannot alias a file descriptor.
    except OSError as exc:
        raise OutputError("cannot inspect stdout: " + str(exc)) from exc
    if stat.S_ISREG(info.st_mode):
        for path in paths:
            try:
                same = os.path.samestat(info, path.stat())
            except FileNotFoundError:
                continue
            if same:
                raise OutputError("stdout aliases an input or report; refusing to append verdict or error to it")


def preflight(outputs, inputs=(), force=False):
    protect_stdout([*inputs, *outputs])
    for i, path in enumerate(outputs):
        if any(aliases(path, source) for source in inputs):
            raise InputError("report output aliases input; refusing even with --force")
        if any(aliases(path, previous) for previous in outputs[:i]):
            raise InputError("report output paths alias each other")
        if not path.parent.is_dir():
            raise InputError("output parent directory does not exist")
        if path.exists() and (not force or not path.is_file()):
            raise InputError("output exists or is not a file; choose a new path or use --force for reports")
        if path.is_symlink():
            raise InputError("output must not be a symbolic link")


def atomic_write(path, text, force=False):
    """Atomic per file, not a multi-file transaction; normal filesystem required."""
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent,
                                         prefix=".vector-audit-", delete=False) as stream:
            temp = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        if force:
            os.replace(temp, path)
        else:
            os.link(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def emit(text):
    try:
        sys.stdout.write(text)
        sys.stdout.flush()
    except (OSError, UnicodeError) as exc:
        # Prevent interpreter shutdown from re-flushing a known failed pipe (rc120).
        # The error is still returned and sent to stderr; this is not a success fallback.
        try:
            fd = sys.stdout.fileno()
            null = os.open(os.devnull, os.O_WRONLY)
            try:
                os.dup2(null, fd)
            finally:
                os.close(null)
        except (OSError, AttributeError, io.UnsupportedOperation):
            sys.stdout = io.StringIO()
        raise OutputError("cannot write verdict to stdout: " + str(exc)) from exc


def emit_error_to_stderr(text, protected_paths=()):
    try:
        try:
            info = os.fstat(sys.stderr.fileno())
        except (AttributeError, io.UnsupportedOperation):
            info = None
        if info is not None and stat.S_ISREG(info.st_mode):
            for path in protected_paths:
                if path.exists() and os.path.samestat(info, path.stat()):
                    return  # Both streams are unsafe: fail via exit code, not input corruption.
        sys.stderr.write(text)
        sys.stderr.flush()
    except (OSError, UnicodeError):
        pass  # Both streams may be gone; the caller still exits with ERROR code 2.
