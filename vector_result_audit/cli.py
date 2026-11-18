"""CLI with conservative output handling. No engine connections or credentials."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from . import __version__, audit_snapshot
from .compare import compare_snapshots
from .report import render_html
from .report_compare import render_comparison_html
from .output import preflight, atomic_write, emit, emit_error_to_stderr, OutputError
from .schema import DEFAULT_MAX_WORK, InputError, read_snapshot


def _json(data):
    return json.dumps(data, indent=2, ensure_ascii=True, allow_nan=False) + "\n"


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
    compare = commands.add_parser("compare", help="gate regressions after proving snapshots comparable")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("candidate", type=Path)
    compare.add_argument("--max-recall-drop", type=float, default=0.0)
    for command in (check, compare):
        command.add_argument("--json", dest="json_path", type=Path)
        command.add_argument("--html", dest="html_path", type=Path)
        command.add_argument("--max-work", type=int, default=DEFAULT_MAX_WORK)
        command.add_argument("--force", action="store_true", help="replace report files, never inputs")
    demo = commands.add_parser("demo", help="create synthetic normal/error controls and actual reports")
    demo.add_argument("--out", required=True, type=Path, help="new output directory; must not already exist")
    args = parser.parse_args(argv)
    protected_paths = []
    try:
        if args.command == "demo":
            args.out.mkdir(parents=False, exist_ok=False)
            outcomes = {}
            for name, data in demo_snapshots().items():
                report = audit_snapshot(data)
                for suffix, text in ((".json", _json(data)), (".report.json", _json(report)), (".html", render_html(report))):
                    atomic_write(args.out / (name + suffix), text)
                outcomes[name] = report["status"]
            emit(_json({"status": "DEMO_READY", "synthetic": True, "audits": outcomes}))
            return 0
        outputs = [path for path in (args.json_path, args.html_path) if path is not None]
        inputs = [args.input] if args.command == "check" else [args.baseline, args.candidate]
        protected_paths = [*inputs, *outputs]
        preflight(outputs, inputs, args.force)
        data, raw = read_snapshot(inputs[0], max_work=args.max_work)
        if args.command == "check":
            report = audit_snapshot(data, max_work=args.max_work)
            report["input_sha256"] = hashlib.sha256(raw).hexdigest()
            renderer = render_html
        else:
            candidate, candidate_raw = read_snapshot(inputs[1], max_work=args.max_work)
            report = compare_snapshots(data, candidate, max_recall_drop=args.max_recall_drop, max_work=args.max_work)
            report["baseline_input_sha256"] = hashlib.sha256(raw).hexdigest()
            report["candidate_input_sha256"] = hashlib.sha256(candidate_raw).hexdigest()
            renderer = render_comparison_html
        if args.json_path:
            atomic_write(args.json_path, _json(report), args.force)
        if args.html_path:
            atomic_write(args.html_path, renderer(report), args.force)
        emit(_json(report))
        return 0 if report["status"] == "PASS" else 1
    except OutputError as exc:
        emit_error_to_stderr(_json({"status": "ERROR", "error": str(exc)}), protected_paths)
        return 2
    except (InputError, OSError, UnicodeError) as exc:
        try:
            emit(_json({"status": "ERROR", "error": str(exc)}))
        except OutputError as output_exc:
            emit_error_to_stderr(_json({"status": "ERROR", "error": str(output_exc)}), protected_paths)
        return 2


if __name__ == "__main__":
    sys.exit(main())
