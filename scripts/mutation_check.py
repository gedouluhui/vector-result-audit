"""Named negative controls in disposable copies. Never edits the source tree."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
# name, product file, old, new, test file, named test. Literal anchors must be unique.
MUTATIONS = [
    ("boundary_overcredit", "audit.py", 'boundary_hits = min(len(counted & boundary), m - len(strict))',
     'boundary_hits = len(counted & boundary)', 'test_audit.py', 'test_boundary_ties_cannot_replace_strictly_better'),
    ("filter_removed", "audit.py", 'eligible = set(distances) if query["eligible_ids"] is None else set(query["eligible_ids"])',
     'eligible = set(distances)', 'test_audit.py', 'test_eligibility_applied_before_top_k'),
    ("duplicate_credit", "audit.py", 'hits = strict_hits + boundary_hits',
     'hits = sum(row["id"] in counted for row in query["results"][:k])', 'test_audit.py', 'test_duplicate_consumes_slot_without_extra_credit'),
    ("reverse_order", "audit.py", 'key=ranks.__getitem__)',
     'key=ranks.__getitem__, reverse=True)', 'test_audit.py', 'test_inner_product_direction_and_score_sign'),
    ("score_check_removed", "audit.py", 'if error > data["score_atol"] + data["score_rtol"] * abs(expected):',
     'if False and error > data["score_atol"] + data["score_rtol"] * abs(expected):', 'test_audit.py', 'test_squared_l2_score_contract'),
    ("cosine_score_cancellation", "distance.py", 'score = similarity if score_kind == "cosine_similarity" else distance',
     'score = 1.0 - distance if score_kind == "cosine_similarity" else distance', 'test_v02_contracts.py', 'test_direct_cosine_score_not_cancelled_by_distance'),
    ("sorted_check_removed", "audit.py", 'if data["require_sorted"]:',
     'if False and data["require_sorted"]:', 'test_v02_contracts.py', 'test_sorting_catches_reverse_even_with_full_recall'),
    ("required_scores_removed", "audit.py", 'if data["require_scores"]:',
     'if False and data["require_scores"]:', 'test_v02_contracts.py', 'test_required_scores_refuse_missing_not_padding'),
    ("incomparable_accepted", "compare.py", 'if canonical_bytes(a[key]) != canonical_bytes(b[key]):',
     'if False and canonical_bytes(a[key]) != canonical_bytes(b[key]):', 'test_compare.py', 'test_corpus_change_refused_before_diff'),
    ("stdout_alias_unprotected", "output.py", 'if same:',
     'if False and same:', 'test_cli_v02.py', 'test_stdout_append_to_input_refused_without_writing_error_to_it'),
    ("invalid_negative_label_padding", "adapters.py", 'if label == -1:',
     'if label < 0:', 'test_adapters.py', 'test_faiss_shape_and_label_errors_not_silently_filtered'),
]


def is_assertion_failure(returncode, output, test_name):
    return (returncode != 0 and f"FAIL: {test_name} (" in output
            and "AssertionError" in output and "FAILED (failures=" in output
            and "ERROR:" not in output and "SyntaxError" not in output)


def fingerprint():
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ("vector_result_audit", "tests", "scripts") for p in sorted((ROOT / folder).glob("*.py"))}


def run():
    original = fingerprint()
    results = []
    with tempfile.TemporaryDirectory(prefix="vector-audit-mutation-") as temp:
        base = Path(temp)
        for folder in ("vector_result_audit", "tests", "scripts"):
            shutil.copytree(ROOT / folder, base / folder, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        env = dict(os.environ, PYTHONPATH=str(base))
        for name, filename, old, new, test_file, test_name in MUTATIONS:
            source = (ROOT / 'vector_result_audit' / filename).read_text(encoding='utf-8')
            if source.count(old) != 1 or old == new:
                raise RuntimeError(f"{name}: mutation anchor is not unique or mutation is a no-op")
            local = base / 'vector_result_audit' / filename
            command = [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", test_file, "-k", test_name, "-v"]
            clean = subprocess.run(command, cwd=base, env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
            if clean.returncode != 0 or "Ran 1 test" not in clean.stderr:
                raise RuntimeError(f"{name}: clean control failed or did not select its named test: {clean.stderr}")
            mutated = source.replace(old, new, 1)
            if mutated == source:
                raise RuntimeError(f"{name}: mutation made no change")
            try:
                local.write_text(mutated, encoding="utf-8", newline="\n")
                bad = subprocess.run(command, cwd=base, env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
            finally:
                local.write_text(source, encoding="utf-8", newline="\n")
                shutil.rmtree(base / 'vector_result_audit' / '__pycache__', ignore_errors=True)
            caught = is_assertion_failure(bad.returncode, bad.stdout + bad.stderr, test_name)
            results.append({"mutation": name, "test": test_name, "caught": caught,
                            "control_returncode": clean.returncode, "mutant_returncode": bad.returncode})
            if not caught:
                print(bad.stdout + bad.stderr, file=sys.stderr)
    if fingerprint() != original:
        raise RuntimeError("source tree changed during verification; result invalid")
    report = {"status": "PASS" if all(item["caught"] for item in results) else "FAIL",
              "caught": sum(item["caught"] for item in results), "total": len(results),
              "source_sha256": original, "results": results}
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(run())
