"""Offline branch coverage for helper error and CLI paths."""
from __future__ import annotations
import importlib.util, json, os
from io import StringIO
from pathlib import Path
import subprocess, sys, tempfile, unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2] / "skills" / "openssf-best-practices"; S=ROOT/'scripts'; sys.path.insert(0,str(S))
def load(name):
 spec=importlib.util.spec_from_file_location(name,S/f'{name}.py'); m=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(m); return m
analyze=load('analyze_best_practices'); score=load('scorecard_runner'); validator=load('validate_best_practices'); approval=load('approval'); safe=load('safe_output')

class AnalyzePaths(unittest.TestCase):
 def test_network_and_summary_helpers(self):
  self.assertEqual(analyze.scorecard_summary({'checks':[{'name':'x','score':1,'reason':'r'}]})['checks'][0]['name'],'x')
  class E: headers={'Location':'https://bestpractices.dev/projects/9'}; status=302
  with patch.object(analyze,'build_opener',return_value=type('O',(),{'open':lambda *_, **__:E()})()): self.assertEqual(analyze.lookup_redirect('https://github.com/a/b')['project_id'],9)
  with patch.object(analyze,'build_opener',return_value=type('O',(),{'open':lambda *_, **__: (_ for _ in ()).throw(analyze.URLError('down'))})()): self.assertEqual(analyze.lookup_redirect('x')['status'],'failed')
  with patch.object(analyze,'urlopen',return_value=type('R',(),{'__enter__':lambda s:s,'__exit__':lambda *a:False,'read':lambda s:-1 and b'{"id":2}'})()): self.assertEqual(analyze.fetch_project(2)['id'],2)
 def test_git_and_write_helpers(self):
  with patch.object(analyze,'run',return_value=subprocess.CompletedProcess([],1,'','bad')): 
   with self.assertRaises(RuntimeError): analyze.tracked_text_files()
  with tempfile.TemporaryDirectory() as temp:
   target=Path(temp)/'x.json'; analyze.write_json(target,{'x':1}); self.assertEqual(json.loads(target.read_text()),{'x':1})
 def test_preflight_and_main_errors(self):
  with patch.object(analyze.shutil,'which',return_value=None),patch('sys.stderr',new_callable=StringIO): self.assertEqual(analyze.preflight(),3)
  with patch.object(sys,'argv',['x','summarize','--project','/missing','--output','/tmp/nope']),patch('sys.stderr',new_callable=StringIO): self.assertEqual(analyze.main(),2)

class AnalyzeCliPaths(unittest.TestCase):
 def test_fetch_discover_and_proposal_clis(self):
  with tempfile.TemporaryDirectory() as temp:
   out=Path(temp)/'out.json'
   with patch.object(analyze,'discover_ids',return_value={'enrolment':'identified'}),patch.object(sys,'argv',['x','discover','--output',str(out)]): self.assertEqual(analyze.main(),0)
   with patch.object(analyze,'fetch_project',return_value={'id':1,'repo_url':'https://github.com/a/b'}),patch.object(sys,'argv',['x','fetch','--project-id','1','--output',str(out)]): self.assertEqual(analyze.main(),0)
   answers=Path(temp)/'a.json'; answers.write_text('{"floss_license_status":"Met"}')
   with patch.object(sys,'argv',['x','proposal-url','--project-id','1','--section','passing','--answers',str(answers)]): self.assertEqual(analyze.main(),0)
 def test_summarize_with_scorecard(self):
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp)/'p.json'; s=Path(temp)/'s.json'; o=Path(temp)/'o.json'; p.write_text('{"id":1,"repo_url":"https://github.com/a/b"}'); s.write_text('{"checks":[]}')
   with patch.object(sys,'argv',['x','summarize','--project',str(p),'--scorecard',str(s),'--output',str(o)]): self.assertEqual(analyze.main(),0)

class ValidatorPaths(unittest.TestCase):
 def test_schema_and_validation_branches(self):
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp)/'x'; p.write_text('{}');
   with self.assertRaises(ValueError): validator.load_schema(p)
  s=validator.load_schema(); self.assertTrue(validator.unsafe_evidence_text('https://localhost/x')); self.assertIsNone(validator.unsafe_evidence_text('plain'))
  self.assertTrue(validator.validate({'description_good_justification':5},s)); self.assertTrue(validator.validate({'name':5},s)); self.assertTrue(validator.validate({'wat':1},s))
 def test_validator_cli_check_and_write(self):
  with tempfile.TemporaryDirectory() as temp:
   p=Path(temp)/'x.json'; p.write_text('{"floss_license_status":"Met"}')
   with patch.object(sys,'argv',['x',str(p)]): self.assertEqual(validator.main(),0)
   with patch.object(sys,'argv',['x',str(p),'--check']): self.assertEqual(validator.main(),0)

class ScorecardPaths(unittest.TestCase):
 def test_token_runtime_and_run_json_paths(self):
  with patch.object(score.subprocess,'run',side_effect=OSError()): self.assertIsNone(score.gh_token())
  with patch.dict(os.environ,{'GITHUB_TOKEN':'abc'},clear=True): self.assertEqual(score.discover_token(),('abc','GITHUB_TOKEN'))
  self.assertEqual(score.redact('abc', 'abc'),'[REDACTED_TOKEN]')
  with tempfile.TemporaryDirectory() as temp:
   out=Path(temp)/'x.json'; cp=subprocess.CompletedProcess([],0,'{}','')
   with patch.object(score.subprocess,'run',return_value=cp): self.assertEqual(score.run_json(['x'],out,{},99,lambda:0),(True,'',False))
   cp=subprocess.CompletedProcess([],1,'','bad')
   with patch.object(score.subprocess,'run',return_value=cp): self.assertEqual(score.run_json(['x'],out,{},99,lambda:0),(False,'bad',False))
 def test_execute_local_paths(self):
  with tempfile.TemporaryDirectory() as temp:
   with patch.object(score,'discover_token',return_value=(None,None)),patch.object(score.shutil,'which',return_value='/bin/scorecard'),patch.object(score,'run_json',return_value=(False,'bad',False)):
    self.assertEqual(score.execute('a/b',Path(temp)/'x',5,None)['status'],'failed')

class ScorecardContainerPaths(unittest.TestCase):
 def test_container_pull_and_run_paths(self):
  with tempfile.TemporaryDirectory() as temp:
   pull=subprocess.CompletedProcess([],0,'','')
   with patch.object(score,'discover_token',return_value=('tok','env')),patch.object(score.shutil,'which',return_value=None),patch.object(score,'working_runtime',return_value=['/bin/docker']),patch.object(score.subprocess,'run',return_value=pull),patch.object(score,'run_json',return_value=(True,'',False)):
    self.assertEqual(score.execute('a/b',Path(temp)/'x',5,None)['status'],'success')
   bad=subprocess.CompletedProcess([],1,'','bad')
   with patch.object(score,'discover_token',return_value=(None,None)),patch.object(score.shutil,'which',return_value=None),patch.object(score,'working_runtime',return_value=['/bin/docker']),patch.object(score.subprocess,'run',return_value=bad):
    self.assertEqual(score.execute('a/b',Path(temp)/'x',5,None)['status'],'failed')

class ScorecardCliPaths(unittest.TestCase):
 def test_main_status_exits(self):
  with patch.object(score,'execute',return_value={'status':'timed_out'}),patch.object(sys,'argv',['x','--repo','a/b','--output','/tmp/x']): self.assertEqual(score.main(),4)
  with patch.object(score,'execute',return_value={'status':'failed'}),patch.object(sys,'argv',['x','--repo','a/b','--output','/tmp/x']): self.assertEqual(score.main(),3)

class FilesystemApprovalPaths(unittest.TestCase):
 def test_safe_and_approval_errors(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp)
   with self.assertRaises(safe.UnsafePathError): safe.atomic_write_text(Path('relative'),'x','x')
   with self.assertRaises(approval.ApprovalError): approval._relative_path('../x')
   p=root/'bad.json'; p.write_text('no')
   with self.assertRaises(approval.ApprovalError): approval.load_approval(p,root)
   with patch.object(approval.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'','')): approval.require_clean_tree(root)
   with patch.object(approval.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'dirty','')):
    with self.assertRaises(approval.ApprovalError): approval.require_clean_tree(root)
   with patch.object(approval.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','bad')):
    with self.assertRaises(approval.ApprovalError): approval.require_clean_tree(root)

if __name__=='__main__': unittest.main()
