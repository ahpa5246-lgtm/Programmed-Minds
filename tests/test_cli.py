import json,subprocess,sys,tempfile,unittest
from unittest.mock import patch
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class CliTests(unittest.TestCase):
 def test_demo_from_module(self):
  with tempfile.TemporaryDirectory() as tmp:
   out=Path(tmp)/'run'
   p=subprocess.run([sys.executable,'-m','programmed_minds','plan','--brief','examples/brief.json','--replay','examples/replay.json','--out',str(out)],cwd=ROOT,text=True,capture_output=True)
   self.assertEqual(p.returncode,0,p.stderr)
   self.assertIn('planned',p.stdout); self.assertEqual(json.loads((out/'manifest.json').read_text())['mode'],'demo')
 def test_missing_brief_actionable_error(self):
  p=subprocess.run([sys.executable,'-m','programmed_minds','plan','--brief','missing.json','--replay','examples/replay.json','--out','runs/no'],cwd=ROOT,text=True,capture_output=True)
  self.assertEqual(p.returncode,2); self.assertIn('Error',p.stderr); self.assertNotIn('Traceback',p.stderr)
 def test_critique_requires_free_endpoint_and_writes_real_review(self):
  from programmed_minds.cli import main
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'brief.json').write_text('{"goal":"x"}');(root/'draft.json').write_text('{"summary":"x"}')
   with patch('programmed_minds.cli.LiveProvider.generate',return_value={
     'data':{'verdict':'approve','summary':'checked','issues':[],'questions':[]},
     'identity':'https://api.groq.com/openai/v1|qwen/qwen3.8-27b','usage':{}}):
    code=main(['critique','--role','improvement_critic','--brief',str(root/'brief.json'),
      '--draft',str(root/'draft.json'),'--config',str(ROOT/'examples/free-critics.json'),'--out',str(root/'review')])
   self.assertEqual(code,0)
   self.assertEqual(json.loads((root/'review/review.json').read_text())['data']['summary'],'checked')
   bad={'roles':{'plan_critic':{'api_style':'chat_completions','api_key_env':'OPENROUTER_API_KEY',
         'base_url':'https://openrouter.ai/api/v1','model':'paid/model'}}}
   (root/'bad.json').write_text(json.dumps(bad))
   code=main(['critique','--role','plan_critic','--brief',str(root/'brief.json'),
     '--draft',str(root/'draft.json'),'--config',str(root/'bad.json'),'--out',str(root/'bad-review')])
   self.assertEqual(code,2);self.assertFalse((root/'bad-review').exists())
if __name__=='__main__': unittest.main()
