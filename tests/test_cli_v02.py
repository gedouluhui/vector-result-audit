import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_audit import snapshot

ROOT=Path(__file__).resolve().parents[1]


class WorkflowCliTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.before=self.folder/'before.json'; self.after=self.folder/'after.json'
        self.before.write_text(json.dumps(snapshot()),encoding='utf-8')
        self.after.write_text(json.dumps(snapshot([{'id':'b'},{'id':'c'}])),encoding='utf-8')
        self.env=dict(os.environ,PYTHONPATH=str(ROOT))

    def command(self,*args):
        return [sys.executable,'-m','vector_result_audit',*map(str,args)]

    def invoke(self,*args,**kwargs):
        return subprocess.run(self.command(*args),cwd=self.folder,env=self.env,capture_output=True,
                              text=True,encoding='utf-8',timeout=30,**kwargs)

    def test_compare_real_files_and_exit_statuses(self):
        out=self.folder/'compare.json'; html=self.folder/'compare.html'
        p=self.invoke('compare',self.before,self.after,'--json',out,'--html',html)
        self.assertEqual(p.returncode,1,p.stderr)
        r=json.loads(out.read_text())
        self.assertEqual(r['queries'][0]['recall_delta'],-0.5)
        self.assertNotEqual(r['baseline_input_sha256'],r['candidate_input_sha256'])
        self.assertIn('Regression',html.read_text(encoding='utf-8'))
        p=self.invoke('compare',self.before,self.after,'--max-recall-drop','0.5')
        self.assertEqual(p.returncode,0,p.stderr)
        data=snapshot(); data['k']=1; self.after.write_text(json.dumps(data))
        p=self.invoke('compare',self.before,self.after)
        self.assertEqual(p.returncode,2)
        self.assertEqual(json.loads(p.stdout)['status'],'ERROR')

    def test_compare_cannot_overwrite_either_source(self):
        a,b=self.before.read_bytes(),self.after.read_bytes()
        for target in (self.before,self.after):
            p=self.invoke('compare',self.before,self.after,'--json',target,'--force')
            self.assertEqual(p.returncode,2)
        self.assertEqual(self.before.read_bytes(),a); self.assertEqual(self.after.read_bytes(),b)

    def test_stdout_append_to_input_refused_without_writing_error_to_it(self):
        original=self.before.read_bytes()
        with self.before.open('ab') as dest:
            p=subprocess.run(self.command('check',self.before),cwd=self.folder,env=self.env,
                             stdout=dest,stderr=subprocess.PIPE,timeout=30)
        self.assertEqual(p.returncode,2)
        self.assertEqual(self.before.read_bytes(),original)
        self.assertEqual(json.loads(p.stderr)['status'],'ERROR')

    def test_stdout_hardlink_to_input_and_report_alias(self):
        alias=self.folder/'alias'
        try:os.link(self.before,alias)
        except OSError:self.skipTest('hardlinks unavailable')
        original=self.before.read_bytes()
        with alias.open('ab') as dest:
            p=subprocess.run(self.command('compare',self.before,self.after),cwd=self.folder,env=self.env,
                             stdout=dest,stderr=subprocess.PIPE,timeout=30)
        self.assertEqual(p.returncode,2);self.assertEqual(self.before.read_bytes(),original)
        out=self.folder/'report.json';out.write_bytes(b'old')
        with out.open('ab') as dest:
            p=subprocess.run(self.command('check',self.before,'--json',out,'--force'),cwd=self.folder,env=self.env,
                             stdout=dest,stderr=subprocess.PIPE,timeout=30)
        self.assertEqual(p.returncode,2);self.assertEqual(out.read_bytes(),b'old')

    def test_closed_reader_pipe_returns_output_error_not_shutdown120(self):
        read_fd,write_fd=os.pipe()
        os.close(read_fd)
        try:
            p=subprocess.run(self.command('check',self.before),cwd=self.folder,env=self.env,
                             stdout=write_fd,stderr=subprocess.PIPE,timeout=30)
        finally:os.close(write_fd)
        self.assertEqual(p.returncode,2,p.stderr)
        self.assertEqual(json.loads(p.stderr)['status'],'ERROR')
        self.assertNotIn(b'Traceback',p.stderr)

    def test_both_diagnostic_streams_aliasing_input_cannot_mutate_it(self):
        original = self.before.read_bytes()
        with self.before.open('ab') as dest:
            p = subprocess.run(self.command('check', self.before), cwd=self.folder, env=self.env,
                               stdout=dest, stderr=dest, timeout=30)
        self.assertEqual(p.returncode, 2)
        self.assertEqual(self.before.read_bytes(), original)

    def test_unrelated_stdout_file_is_supported(self):
        out=self.folder/'stdout.json'
        with out.open('wb') as dest:
            p=subprocess.run(self.command('check',self.before),cwd=self.folder,env=self.env,
                             stdout=dest,stderr=subprocess.PIPE,timeout=30)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(out.read_text())['status'],'PASS')


if __name__=='__main__':unittest.main()
