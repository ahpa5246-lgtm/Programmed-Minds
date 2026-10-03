import os,sys,unittest
import json
from pathlib import Path
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
 def test_free_critics_use_distinct_chat_endpoints_and_validate_review(self):
  config=json.loads((Path(__file__).resolve().parents[1]/'examples/free-critics.json').read_text())
  calls=[]
  def factory(**kwargs):
   def create(**request):
    calls.append((kwargs,request))
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"verdict":"approve","summary":"ok","issues":[],"questions":[]}'))],usage=SimpleNamespace(prompt_tokens=9,completion_tokens=8))
   return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
  with patch.dict(sys.modules,{'openai':SimpleNamespace(OpenAI=factory)}),patch.dict(os.environ,{'OPENROUTER_API_KEY':'route-secret','GROQ_API_KEY':'groq-secret'}):
   provider=LiveProvider(config)
   a=provider.generate('research_critic',Review,{'draft':{}})
   b=provider.generate('improvement_critic',Review,{'draft':{}})
  self.assertEqual([a['data']['verdict'],b['data']['verdict']],['approve','approve'])
  self.assertNotEqual(a['identity'],b['identity'])
  self.assertEqual([r['model'] for _,r in calls],['z-ai/glm-5.3-flash:free','qwen/qwen3.8-27b'])
  self.assertEqual([r['response_format']['type'] for _,r in calls],['json_object','json_object'])
  self.assertEqual(a['usage'],{'input_tokens':9,'output_tokens':8})
  self.assertNotIn('secret',str(a)+str(b))
 def test_chat_critic_invalid_review_fails_closed(self):
  reply=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"verdict":"approve","issues":[]}'))],usage=None)
  client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw:reply)))
  config={'default':{'model':'any'},'roles':{'plan_critic':{'api_style':'chat_completions'}}}
  with patch.dict(sys.modules,{'openai':SimpleNamespace(OpenAI=lambda **kw:client)}),patch.dict(os.environ,{'OPENAI_API_KEY':'secret'}):
   with self.assertRaisesRegex(ProviderError,'Invalid.*response'): LiveProvider(config).generate('plan_critic',Review,{})
 def test_chat_critic_cannot_enable_unverified_web_search(self):
  config={'default':{'model':'any'},'roles':{'researcher':{'api_style':'chat_completions'}}}
  with patch.dict(os.environ,{'OPENAI_API_KEY':'secret'}):
   with self.assertRaisesRegex(ProviderError,'source_urls'): LiveProvider(config).generate('researcher',Research,{})
 def test_free_config_uses_distinct_models_and_no_openai_key(self):
  config=json.loads((Path(__file__).resolve().parents[1]/'examples/fully-free.json').read_text())
  provider=LiveProvider(config)
  with patch.dict(os.environ,{'GROQ_API_KEY':'groq','OPENROUTER_API_KEY':'route'},clear=True):
   for producer,critic in [('researcher','research_critic'),('improver','improvement_critic'),('planner','plan_critic')]:
    p=provider._settings(producer); c=provider._settings(critic)
    self.assertNotEqual((p[1],p[2]),(c[1],c[2]))
    self.assertNotIn('OPENAI_API_KEY',(p[0]['api_key_env'],c[0]['api_key_env']))
 def test_free_sources_require_competition_rules_and_https(self):
  from programmed_minds.provider import supplied_evidence
  with self.assertRaisesRegex(ProviderError,'rules_url'):
   supplied_evidence({'source_urls':['https://example.com'],'competition':{'rules_url':'https://example.org'}})
  with self.assertRaisesRegex(ProviderError,'HTTPS'):
   supplied_evidence({'source_urls':['http://example.com']})
if __name__=='__main__': unittest.main()
