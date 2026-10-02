import copy, json, tempfile, unittest
from pathlib import Path
from programmed_minds.pipeline import run_pipeline,run_audit,load_approved,PipelineError
from programmed_minds.provider import ReplayProvider
FIXTURE=Path(__file__).resolve().parents[1]/'examples/replay.json'
class AuditTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
  self.root=Path(self.tmp.name); self.fixture=json.loads(FIXTURE.read_text())
  run_pipeline({'goal':'Demo'},ReplayProvider(self.fixture),self.root/'run')
 def test_demo_and_missing_browser_never_pass(self):
  result=run_audit(self.root/'run',{'status':'passed','checks':[]},ReplayProvider(self.fixture),self.root/'audit')
  self.assertEqual(result['status'],'blocked'); self.assertFalse(result['release_approved'])
  self.assertTrue(any('Demo' in reason for reason in result['reasons']))
 def test_edited_approved_artifact_rejected(self):
  path=self.root/'run/approved.json'; data=json.loads(path.read_text()); data['planner']['architecture']='Tampered'
  path.write_text(json.dumps(data))
  with self.assertRaises(PipelineError): load_approved(self.root/'run')
 def test_invalid_report_hash_rejected(self):
  report={'status':'passed','checks':[{'name':'gitleaks','status':'passed','required':True,'returncode':0}],'sha256':'fake'}
  result=run_audit(self.root/'run',report,ReplayProvider(self.fixture),self.root/'audit')
  self.assertEqual(result['status'],'blocked')
  self.assertTrue(any('integrity' in reason for reason in result['reasons']))
 def test_pass_claim_without_exit_zero_rejected(self):
  report={'status':'passed','checks':[{'name':'gitleaks','status':'passed','required':True,'returncode':9}]}
  result=run_audit(self.root/'run',report,ReplayProvider(self.fixture),self.root/'audit')
  self.assertEqual(result['status'],'blocked'); self.assertTrue(any('exit' in reason for reason in result['reasons']))
if __name__=='__main__': unittest.main()

class ReviewRegressions(unittest.TestCase):
 def test_scanner_cannot_certify_ui_acceptance(self):
  from programmed_minds.pipeline import digest
  import hashlib
  fixture=json.loads(FIXTURE.read_text())
  for gate in fixture['planner'][0]['data']['gates']: gate['required']=gate['tool']=='gitleaks'
  fixture['tester'][0]['data'].update(verdict='pass',gaps=[],cases=[{'requirement_id':'R1','scenario':'Save and reload browser','steps':['save','reload'],'expected':'persist','evidence':'gitleaks','status':'passed'}])
  p=ReplayProvider(fixture); p.mode='live'
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); run_pipeline({'goal':'UI persistence'},p,root/'run')
   report={'status':'passed','checks':[{'name':'gitleaks','status':'passed','required':True,'requirement_ids':['R1'],'returncode':0}]}
   report['sha256']=hashlib.sha256(json.dumps(report,sort_keys=True,separators=(',',':')).encode()).hexdigest()
   result=run_audit(root/'run',report,p,root/'audit')
   self.assertEqual(result['status'],'blocked')
 def test_planning_rejects_symlink_ancestor(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp); (root/'real').mkdir(); (root/'alias').symlink_to(root/'real',target_is_directory=True)
   with self.assertRaises(PipelineError): run_pipeline({'goal':'Goal'},ReplayProvider(json.loads(FIXTURE.read_text())),root/'alias/run')

class ExecutedEvidenceTests(unittest.TestCase):
 def setup_run(self,root):
  fixture=json.loads(FIXTURE.read_text())
  req=fixture['improver'][0]['data']['requirements'][0]
  req.update(description='Persist a result file',acceptance='Read the value after reopening',evidence_tool='python-tests',test_id='test_accept.Accept.test_save')
  for gate in fixture['planner'][0]['data']['gates']: gate['required']=False
  fixture['tester'][0]['data'].update(verdict='pass',gaps=[],cases=[{'requirement_id':'R1','scenario':'Reopen result file','steps':['save','reopen'],'expected':'persist','evidence':'python-tests','status':'passed'}])
  p=ReplayProvider(fixture);p.mode='live'
  run_pipeline({'goal':'Persist results'},p,root/'run')
  return p
 def report(self,root):
  from programmed_minds.checks import run_checks
  target=root/'هدف';(target/'tests').mkdir(parents=True)
  (target/'tests/test_accept.py').write_text('import unittest,tempfile\nfrom pathlib import Path\nclass Accept(unittest.TestCase):\n def test_save(self):\n  with tempfile.TemporaryDirectory() as t:\n   p=Path(t)/"result.txt"; p.write_text("42"); self.assertEqual(p.read_text(),"42")\n')
  return run_checks(target,{'checks':[{'name':'python-tests','requirement_ids':['R1'],'reason':'دليل عربي'}]},root/'checks')
 def test_actual_unicode_report_and_exact_test_evidence_can_verify(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p=self.setup_run(root);report=self.report(root)
   result=run_audit(root/'run',report,p,root/'audit',report_dir=root/'checks')
   self.assertEqual(result['status'],'verified',result['reasons'])
   self.assertFalse(result['release_approved'])
 def test_modified_log_cannot_certify(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p=self.setup_run(root);report=self.report(root)
   (root/'checks'/report['checks'][0]['log']).write_text('fabricated output')
   result=run_audit(root/'run',report,p,root/'audit',report_dir=root/'checks')
   self.assertEqual(result['status'],'blocked')
 def test_wrong_test_id_cannot_certify(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p=self.setup_run(root);report=self.report(root)
   report['checks'][0]['test_results']=[{'id':'some_unrelated_test','status':'passed'}]
   import hashlib
   report['sha256']=hashlib.sha256(json.dumps({k:v for k,v in report.items() if k!='sha256'},sort_keys=True,separators=(',',':')).encode()).hexdigest()
   self.assertEqual(run_audit(root/'run',report,p,root/'audit',report_dir=root/'checks')['status'],'blocked')
