import json,subprocess,sys,tempfile,unittest
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
if __name__=='__main__': unittest.main()
