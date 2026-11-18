import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


class DeliveryScriptTests(unittest.TestCase):
    def test_public_demo_is_generated_and_refuses_clobber(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'demo.html'
            command=[sys.executable,'-m','scripts.build_demo','--out',str(out)]
            p=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=30)
            self.assertEqual(p.returncode,0,p.stderr)
            html=out.read_text(encoding='utf-8')
            self.assertIn('Synthetic example',html)
            self.assertIn('Missing strictly-better neighbors',html)
            self.assertIn('-0.5',html)
            self.assertNotIn('<script',html)
            p=subprocess.run([*command,'--check'],cwd=ROOT,capture_output=True)
            self.assertEqual(p.returncode,0)
            out.write_text('sentinel')
            self.assertNotEqual(subprocess.run(command,cwd=ROOT,capture_output=True).returncode,0)
            self.assertNotEqual(subprocess.run([*command,'--check'],cwd=ROOT,capture_output=True).returncode,0)
            self.assertEqual(out.read_text(),'sentinel')

    def test_ci_evidence_keeps_pass_fail_and_error_distinct(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'evidence'
            p=subprocess.run([sys.executable,str(ROOT/'scripts/ci_evidence.py'),'--out',str(out)],cwd=ROOT,
                             capture_output=True,text=True,timeout=30)
            self.assertEqual(p.returncode,0,p.stderr)
            receipt=json.loads((out/'receipt.json').read_text())
            self.assertEqual(receipt['exit_codes'],{'baseline':0,'candidate':1,'comparison':1,'incomparable':2})
            self.assertEqual(json.loads((out/'comparison.json').read_text())['status'],'FAIL')
            self.assertTrue((out/'comparison.html').is_file())
            again=subprocess.run([sys.executable,str(ROOT/'scripts/ci_evidence.py'),'--out',str(out)],cwd=ROOT,capture_output=True)
            self.assertNotEqual(again.returncode,0)
