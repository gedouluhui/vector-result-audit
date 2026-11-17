import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from scripts.mutation_check import is_assertion_failure


class MutationHarnessTests(unittest.TestCase):
    def test_accepts_named_assertion_failure_only(self):
        output = 'FAIL: test_guard (test_case.Tests.test_guard)\nAssertionError: 1 != 2\nFAILED (failures=1)'
        self.assertTrue(is_assertion_failure(1, output, 'test_guard'))
        self.assertFalse(is_assertion_failure(0, output, 'test_guard'))
        self.assertFalse(is_assertion_failure(1, output, 'different_test'))
        self.assertFalse(is_assertion_failure(1, output.replace('AssertionError', 'ValueError'), 'test_guard'))

    def test_real_import_failure_is_not_a_caught_mutation(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='vra-import-control-') as tmp:
            folder = Path(tmp)
            shutil.copytree(root / 'vector_result_audit', folder / 'vector_result_audit',
                            ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            (folder / 'tests').mkdir()
            shutil.copyfile(root / 'tests/test_audit.py', folder / 'tests/test_audit.py')
            target = folder / 'vector_result_audit/__init__.py'
            baseline = target.read_text(encoding='utf-8')
            broken = "raise ImportError('known-import-negative-control')\n"
            self.assertNotEqual(baseline, broken)
            target.write_text(broken, encoding='utf-8', newline='\n')
            name = 'test_squared_l2_score_contract'
            command = [sys.executable, '-B', '-m', 'unittest', 'discover', '-s', 'tests',
                       '-p', 'test_audit.py', '-k', name, '-v']
            proc = subprocess.run(command, cwd=folder, env=dict(os.environ, PYTHONPATH=str(folder)),
                                  capture_output=True, text=True, encoding='utf-8', timeout=30)
            output = proc.stdout + proc.stderr
            self.assertNotEqual(proc.returncode, 0)
            self.assertFalse(is_assertion_failure(proc.returncode, output, name), output)
            self.assertIn('known-import-negative-control', output)

    def test_crashes_and_passes_never_count_as_caught(self):
        for output in ('SyntaxError: invalid syntax', 'ERROR: test_guard\nImportError\nFAILED (errors=1)',
                       'test_guard ... ok\nOK', 'FAIL: test_guard\nAssertionError\nERROR: another\nFAILED (failures=1, errors=1)'):
            with self.subTest(output=output):
                self.assertFalse(is_assertion_failure(1, output, 'test_guard'))
