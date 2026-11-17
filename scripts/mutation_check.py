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
MUTATIONS = [
    ("boundary_overcredit", 'boundary_hits = min(len(counted & boundary), m - len(strict))',
     'boundary_hits = len(counted & boundary)', 'test_boundary_ties_cannot_replace_strictly_better'),
    ("filter_removed", 'eligible = set(distances) if query["eligible_ids"] is None else set(query["eligible_ids"])',
     'eligible = set(distances)', 'test_eligibility_applied_before_top_k'),
    ("duplicate_credit", 'hits = strict_hits + boundary_hits',
     'hits = sum(row["id"] in counted for row in query["results"][:k])', 'test_duplicate_consumes_slot_without_extra_credit'),
    ("reverse_order", 'key=distances.__getitem__)',
     'key=distances.__getitem__, reverse=True)', 'test_inner_product_direction_and_score_sign'),
    ("score_check_removed", 'if error > data["score_atol"] + data["score_rtol"] * abs(expected):',
     'if False and error > data["score_atol"] + data["score_rtol"] * abs(expected):', 'test_squared_l2_score_contract'),
]


def is_assertion_failure(returncode, output, test_name):
    return (returncode != 0 and f"FAIL: {test_name} (" in output
            and "AssertionError" in output and "FAILED (failures=" in output
            and "ERROR:" not in output and "SyntaxError" not in output)


def fingerprint():
    return {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_bytes()).hexdigest()
            for folder in ("vector_result_audit", "tests", "scripts") for p in sorted((ROOT / folder).glob("*.py"))}


def run():
    original = fingerprint()
    target = ROOT / "vector_result_audit" / "audit.py"
    source = target.read_text(encoding="utf-8")
    results = []
    with tempfile.TemporaryDirectory(prefix="vector-audit-mutation-") as temp:
        base = Path(temp)
        for folder in ("vector_result_audit", "tests", "scripts"):
            shutil.copytree(ROOT / folder, base / folder, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        env = dict(os.environ, PYTHONPATH=str(base))
        for name, old, new, test_name in MUTATIONS:
            if source.count(old) != 1 or old == new:
                raise RuntimeError(f"{name}: mutation anchor is not unique or mutation is a no-op")
            local = base / "vector_result_audit" / "audit.py"
            local.write_text(source, encoding="utf-8", newline="\n")
            shutil.rmtree(base / "vector_result_audit" / "__pycache__", ignore_errors=True)
            command = [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-p", "test_audit.py", "-k", test_name, "-v"]
            clean = subprocess.run(command, cwd=base, env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
            if clean.returncode != 0 or "Ran 1 test" not in clean.stderr:
                raise RuntimeError(f"{name}: clean control failed or did not select its named test: {clean.stderr}")
            mutated = source.replace(old, new, 1)
            if mutated == source:
                raise RuntimeError(f"{name}: mutation made no change")
            local.write_text(mutated, encoding="utf-8", newline="\n")
            bad = subprocess.run(command, cwd=base, env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)
            caught = is_assertion_failure(bad.returncode, bad.stdout + bad.stderr, test_name)
            results.append({"mutation": name, "test": test_name, "caught": caught, "control_returncode": clean.returncode,
                            "mutant_returncode": bad.returncode})
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
