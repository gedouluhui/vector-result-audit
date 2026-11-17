import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_audit import snapshot
from vector_result_audit import InputError, audit_snapshot
from vector_result_audit.schema import load_snapshot

ROOT = Path(__file__).resolve().parents[1]


class FileTests(unittest.TestCase):
    def test_duplicate_keys_nonfinite_invalid_encoding_and_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.json"
            for content in (b'{"k":1,"k":2}', b'{"x": NaN}', b'\xff', b'[]'):
                path.write_bytes(content)
                with self.subTest(content=content), self.assertRaises(InputError):
                    load_snapshot(path)
            path.write_text(json.dumps(snapshot()), encoding="utf-8")
            with self.assertRaises(InputError):
                load_snapshot(path, max_bytes=3)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.case = self.folder / "case.json"
        self.case.write_text(json.dumps(snapshot()), encoding="utf-8")

    def run_cli(self, *args):
        env = dict(os.environ, PYTHONPATH=str(ROOT))
        return subprocess.run([sys.executable, "-m", "vector_result_audit", *map(str, args)], cwd=self.folder,
                              env=env, capture_output=True, text=True, encoding="utf-8", timeout=30)

    def test_real_cli_pass_fail_and_error(self):
        proc = self.run_cli("check", self.case)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["input_sha256"], hashlib.sha256(self.case.read_bytes()).hexdigest())
        self.case.write_text(json.dumps(snapshot([{"id": "a"}, {"id": "a"}])), encoding="utf-8")
        proc = self.run_cli("check", self.case)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["status"], "FAIL")
        proc = self.run_cli("check", self.case, "--max-work", "1")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(json.loads(proc.stdout)["status"], "ERROR")

    def test_report_files_and_no_overwrite(self):
        out, html = self.folder / "report.json", self.folder / "report.html"
        proc = self.run_cli("check", self.case, "--json", out, "--html", html)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(out.read_text())["status"], "PASS")
        self.assertIn("Vector Result Audit", html.read_text(encoding="utf-8"))
        out.write_text("sentinel", encoding="utf-8")
        proc = self.run_cli("check", self.case, "--json", out)
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(out.read_text(), "sentinel")
        self.assertEqual(self.run_cli("check", self.case, "--json", out, "--force").returncode, 0)

    def test_input_output_alias_and_preflight_collision(self):
        original = self.case.read_bytes()
        self.assertEqual(self.run_cli("check", self.case, "--json", self.case, "--force").returncode, 2)
        self.assertEqual(self.case.read_bytes(), original)
        out = self.folder / "new.json"
        self.assertEqual(self.run_cli("check", self.case, "--json", out, "--html", out).returncode, 2)
        self.assertFalse(out.exists())
        occupied = self.folder / "occupied.html"
        occupied.write_text("keep", encoding="utf-8")
        self.assertEqual(self.run_cli("check", self.case, "--json", out, "--html", occupied).returncode, 2)
        self.assertFalse(out.exists())
        self.assertEqual(occupied.read_text(), "keep")

    def test_hardlink_input_alias_blocked(self):
        alias = self.folder / "alias.json"
        try:
            os.link(self.case, alias)
        except OSError:
            self.skipTest("filesystem does not support hardlinks")
        original = self.case.read_bytes()
        self.assertEqual(self.run_cli("check", self.case, "--json", alias, "--force").returncode, 2)
        self.assertEqual(self.case.read_bytes(), original)

    def test_invalid_input_cannot_leave_pass_file(self):
        self.case.write_text('{"k":1,"k":2}', encoding="utf-8")
        out = self.folder / "new.json"
        self.assertEqual(self.run_cli("check", self.case, "--json", out).returncode, 2)
        self.assertFalse(out.exists())

    def test_demo_generates_real_audits_and_refuses_existing(self):
        out = self.folder / "demo"
        proc = self.run_cli("demo", "--out", out)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for name, status in (("clean", "PASS"), ("broken", "FAIL")):
            data = load_snapshot(out / (name + ".json"))
            actual = audit_snapshot(data)
            stored = json.loads((out / (name + ".report.json")).read_text())
            self.assertEqual(actual, stored)
            self.assertEqual(actual["status"], status)
        self.assertEqual(self.run_cli("demo", "--out", out).returncode, 2)


if __name__ == "__main__":
    unittest.main()
