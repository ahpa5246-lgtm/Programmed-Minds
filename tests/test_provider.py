import os,sys,unittest
from types import SimpleNamespace
from unittest.mock import patch
from programmed_minds.provider import LiveProvider,ProviderError
from programmed_minds.models import Review,Research
class ProviderTests(unittest.TestCase):
 def provider(self,**kwargs):
  return LiveProvider({'default':{'model':'test-model'},**kwargs})
 def test_no_key_actionable(self):
  with patch.dict(os.environ,{},clear=True):
   with self.assertRaises(ProviderError): self.provider()._settings('planner')
 def test_credentials_in_endpoint_rejected(self):
  with patch.dict(os.environ,{'OPENAI_API_KEY':'private'}):
   with self.assertRaises(ProviderError): LiveProvider({'default':{'model':'x','base_url':'https://u:secret@example.com/v1'}})._settings('planner')
 def test_sdk_structured_request_and_no_key_in_result(self):
  requests=[]
  response=SimpleNamespace(status='completed',output_text='{"verdict":"approve","summary":"review","issues":[],"questions":[]}',usage=SimpleNamespace(input_tokens=2,output_tokens=3))
  client=SimpleNamespace(responses=SimpleNamespace(create=lambda **kw:(requests.append(kw) or response)))
  with patch.dict(sys.modules,{'openai':SimpleNamespace(OpenAI=lambda **kw:client)}),patch.dict(os.environ,{'OPENAI_API_KEY':'private'}):
   result=self.provider().generate('plan_critic',Review,{'draft':{}})
  self.assertTrue(requests[0]['text']['format']['strict']); self.assertFalse(requests[0]['store'])
  self.assertNotIn('private',str(result)); self.assertEqual(result['usage']['output_tokens'],3)
 def test_missing_search_evidence_rejected(self):
  response=SimpleNamespace(output_text='Unsupported assertion',model_dump=lambda:{'output':[]})
  client=SimpleNamespace(responses=SimpleNamespace(create=lambda **kw:response))
  with patch.dict(sys.modules,{'openai':SimpleNamespace(OpenAI=lambda **kw:client)}),patch.dict(os.environ,{'OPENAI_API_KEY':'private'}):
   with self.assertRaisesRegex(ProviderError,'no observed'): self.provider().generate('researcher',Research,{})
 def test_budget_enforced_before_request(self):
  client=SimpleNamespace(responses=SimpleNamespace(create=lambda **kw:object()))
  p=self.provider(max_calls=1); p._call(client,model='x')
  with self.assertRaisesRegex(ProviderError,'budget'): p._call(client,model='x')
 def test_failure_does_not_expose_exception_payload(self):
  def fail(**kwargs): raise RuntimeError('private-token-and-prompt')
  client=SimpleNamespace(responses=SimpleNamespace(create=fail))
  with self.assertRaises(ProviderError) as caught: self.provider()._call(client,model='x')
  self.assertNotIn('private',str(caught.exception))
if __name__=='__main__': unittest.main()
