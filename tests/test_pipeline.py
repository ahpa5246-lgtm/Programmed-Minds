import copy
import json
import tempfile
import unittest
from pathlib import Path
from programmed_minds.pipeline import run_pipeline, PipelineError
from programmed_minds.provider import ReplayProvider
FIXTURE = Path(__file__).resolve().parents[1] / 'examples' / 'replay.json'
class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / 'run'
        self.fixture = json.loads(FIXTURE.read_text())
    def run_with(self, **kwargs):
        return run_pipeline({'goal':'Build an Iraqi learning tool','requirements':['Arabic']},ReplayProvider(self.fixture),self.out,**kwargs)
    def test_agents_and_immutable_traces(self):
        result=self.run_with()
        self.assertEqual(result['status'],'planned'); self.assertEqual(result['mode'],'demo')
        self.assertEqual(len(result['stages']),7); self.assertFalse(result['release_approved'])
        self.assertTrue((self.out/'HANDOFF.md').exists())
        for stage in result['stages']:
            artifact=json.loads((self.out/stage['artifact']).read_text())
            self.assertEqual(len(artifact['input_hash']),64); self.assertEqual(len(artifact['output_hash']),64)
    def test_critical_issue_overrides_approve_and_revises(self):
        bad=copy.deepcopy(self.fixture['research_critic'][0]); bad['data']['issues']=[{'severity':'critical','claim':'Wrong audience','evidence':'Brief specifies beginners','fix':'Reconsider audience'}]
        bad['data']['verdict']='approve'; self.fixture['research_critic'].insert(0,bad)
        self.fixture['researcher'].append(copy.deepcopy(self.fixture['researcher'][0]))
        self.assertEqual(len(self.run_with()['stages']),9)
    def test_reject_stops_downstream(self):
        self.fixture['research_critic'][0]['data']['verdict']='reject'
        result=self.run_with(); self.assertEqual(result['status'],'blocked'); self.assertEqual(len(result['stages']),2)
        self.assertFalse((self.out/'HANDOFF.md').exists())
    def test_revision_budget_stops(self):
        self.fixture['research_critic'][0]['data']['verdict']='revise'
        result=self.run_with(max_revisions=0); self.assertEqual(result['status'],'blocked'); self.assertEqual(len(result['stages']),2)
    def test_unobserved_source_blocks(self):
        self.fixture['researcher'][0]['evidence_urls']=[]
        result=self.run_with(); self.assertEqual(result['status'],'blocked'); self.assertIn('observed',result['error'])
    def test_same_identity_strict_mode_blocked(self):
        self.fixture['research_critic'][0]['identity']=self.fixture['researcher'][0]['identity']
        self.assertEqual(self.run_with(strict_diversity=True)['status'],'blocked')
    def test_duplicate_run_directory_rejected(self):
        self.run_with()
        with self.assertRaises(PipelineError): self.run_with()
    def test_unknown_output_fields_block(self):
        self.fixture['researcher'][0]['data']['shell']='danger'
        self.assertEqual(self.run_with()['status'],'blocked')
    def test_task_dependency_cycle_block(self):
        tasks=self.fixture['planner'][0]['data']['tasks']; tasks[0]['depends_on']=[tasks[0]['id']]
        self.assertEqual(self.run_with()['status'],'blocked')
    def test_missing_tool_decision_blocks(self):
        self.fixture['planner'][0]['data']['gates'].pop()
        self.assertEqual(self.run_with()['status'],'blocked')
    def test_source_javascript_rejected(self):
        self.fixture['researcher'][0]['data']['sources'][0]['url']='javascript:alert(1)'
        self.fixture['researcher'][0]['evidence_urls']=['javascript:alert(1)']
        self.assertEqual(self.run_with()['status'],'blocked')
if __name__=='__main__': unittest.main()
