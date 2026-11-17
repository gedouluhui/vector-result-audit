"""CLI with conservative output handling. No engine connections or credentials."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

from . import __version__, audit_snapshot
from .report import render_html
from .schema import DEFAULT_MAX_WORK, InputError, read_snapshot


def _json(data):
    return json.dumps(data, indent=2, ensure_ascii=True, allow_nan=False) + "\n"


def _aliases(a, b):
    if a.resolve() == b.resolve():
        return True
    return a.exists() and b.exists() and os.path.samefile(a, b)


def _preflight(outputs, input_path=None, force=False):
    for i, path in enumerate(outputs):
        if input_path is not None and _aliases(path, input_path):
            raise InputError("report output aliases input; refusing even with --force")
        if any(_aliases(path, previous) for previous in outputs[:i]):
            raise InputError("report output paths alias each other")
        if not path.parent.is_dir():
            raise InputError("output parent directory does not exist")
        if path.exists() and (not force or not path.is_file()):
            raise InputError("output exists or is not a file; choose a new path or use --force for reports")
        if path.is_symlink():
            raise InputError("output must not be a symbolic link")


def _atomic_write(path, text, force=False):
    """Atomic per file. Multiple reports are not a filesystem transaction."""
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
            # Atomic no-clobber installation; supported on NTFS and normal POSIX filesystems.
            os.link(temp, path)
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)


def demo_snapshots():
    """Synthetic controls, deliberately not recordings from a database."""
    corpus = [{"id": "closest", "vector": [0, 0]}, {"id": "tie-east", "vector": [1, 0]},
              {"id": "tie-west", "vector": [-1, 0]}, {"id": "filtered", "vector": [0, 0.25]}]
    base = {"schema_version": 1, "metric": "l2", "score_kind": "squared_l2", "k": 2,
            "min_recall": 1.0, "corpus": corpus}
    clean = {**base, "queries": [{"id": "synthetic-valid-tie", "vector": [0, 0],
              "eligible_ids": ["closest", "tie-east", "tie-west"],
              "results": [{"id": "closest", "score": 0}, {"id": "tie-west", "score": 1}]}]}
    broken = {**base, "queries": [
        {"id": "synthetic-boundary-trap", "vector": [0, 0], "eligible_ids": ["closest", "tie-east", "tie-west"],
         "results": [{"id": "tie-east", "score": 1}, {"id": "tie-west", "score": 1}]},
        {"id": "synthetic-filter-leak", "vector": [0, 0], "eligible_ids": ["closest", "tie-east", "tie-west"],
         "results": [{"id": "filtered", "score": 0.25}, {"id": "closest", "score": 0}]},
        {"id": "synthetic-duplicate", "vector": [0, 0], "eligible_ids": None,
         "results": [{"id": "closest", "score": 0}, {"id": "closest", "score": 0}]}]}
    return {"clean": clean, "broken": broken}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline vector-result contracts, not embedding relevance.")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="audit one explicit JSON snapshot")
    check.add_argument("input", type=Path)
    check.add_argument("--json", dest="json_path", type=Path)
    check.add_argument("--html", dest="html_path", type=Path)
    check.add_argument("--max-work", type=int, default=DEFAULT_MAX_WORK)
    check.add_argument("--force", action="store_true", help="replace report files, never the input")
    demo = commands.add_parser("demo", help="create synthetic normal/error controls and actual reports")
    demo.add_argument("--out", required=True, type=Path, help="new output directory; must not already exist")
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            args.out.mkdir(parents=False, exist_ok=False)
            outcomes = {}
            for name, data in demo_snapshots().items():
                report = audit_snapshot(data)
                for suffix, text in ((".json", _json(data)), (".report.json", _json(report)), (".html", render_html(report))):
                    _atomic_write(args.out / (name + suffix), text)
                outcomes[name] = report["status"]
            print(_json({"status": "DEMO_READY", "synthetic": True, "audits": outcomes}), end="")
            return 0
        outputs = [path for path in (args.json_path, args.html_path) if path is not None]
        _preflight(outputs, args.input, args.force)
        data, raw = read_snapshot(args.input, max_work=args.max_work)
        report = audit_snapshot(data, max_work=args.max_work)
        report["input_sha256"] = hashlib.sha256(raw).hexdigest()
        if args.json_path:
            _atomic_write(args.json_path, _json(report), args.force)
        if args.html_path:
            _atomic_write(args.html_path, render_html(report), args.force)
        print(_json(report), end="")
        return 0 if report["status"] == "PASS" else 1
    except (InputError, OSError, UnicodeError) as exc:
        print(_json({"status": "ERROR", "error": str(exc)}), end="")
        return 2


if __name__ == "__main__":
    sys.exit(main())
