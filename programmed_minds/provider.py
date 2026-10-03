"""Official SDK inference and deterministic offline replay, imported lazily."""
import copy
import json
import os
import ipaddress
import socket
from html.parser import HTMLParser
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlsplit
from .prompts import COMMON, ROLE_PROMPTS

class ProviderError(RuntimeError): pass

class _Text(HTMLParser):
    def __init__(self): super().__init__(); self.parts=[]; self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'): self.hidden+=1
    def handle_endtag(self,tag):
        if tag in ('script','style') and self.hidden: self.hidden-=1
    def handle_data(self,data):
        if not self.hidden: self.parts.append(data)

class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

def supplied_evidence(brief):
    urls=brief.get('source_urls',[])
    if not isinstance(urls,list) or not 1<=len(urls)<=8 or any(not isinstance(u,str) for u in urls):
        raise ProviderError('Free live research needs 1-8 source_urls in the brief')
    rules=brief.get('competition',{}).get('rules_url')
    if rules and rules not in urls: raise ProviderError('Include competition.rules_url in source_urls')
    observed=[]; excerpts=[]
    for url in urls:
        parsed=urlsplit(url)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None,443) or len(url)>2048:
            raise ProviderError('Source URLs must be public HTTPS pages')
        try:
            addresses=socket.getaddrinfo(parsed.hostname,443,type=socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
                raise ProviderError('Source URLs must be public HTTPS pages')
            with build_opener(_NoRedirect).open(Request(url,headers={'User-Agent':'Programmed-Minds/1.0'}),timeout=12) as response:
                kind=response.headers.get_content_type()
                if kind not in ('text/html','text/plain'): raise ProviderError('Source URL must return HTML or plain text')
                raw=response.read(150001)
                if len(raw)>150000: raise ProviderError('Source page too large')
                body=raw.decode('utf-8',errors='replace')
                if kind=='text/html':
                    parser=_Text(); parser.feed(body); body=' '.join(parser.parts)
                observed.append(url); excerpts.append({'url':url,'text':' '.join(body.split())[:16000]})
        except ProviderError: raise
        except Exception: raise ProviderError('Could not read supplied source URL; use a public HTML page') from None
    return observed,excerpts

class ReplayProvider:
    mode='demo'
    def __init__(self,responses):
        self.responses=copy.deepcopy(responses)
    def generate(self,role,schema,context):
        queue=self.responses.get(role,[])
        if not queue: raise ProviderError('Replay exhausted for '+role)
        return queue.pop(0)

class LiveProvider:
    mode='live'
    def __init__(self,config):
        self.config=config
        self.calls=0
        self.max_calls=int(config.get('max_calls',30))
        self.tokens=int(config.get('max_output_tokens',4000))
        if not 1<=self.max_calls<=100 or not 128<=self.tokens<=32000:
            raise ProviderError('Invalid call/token budget')
    def _settings(self,role):
        settings=dict(self.config.get('default',{})); settings.update(self.config.get('roles',{}).get(role,{}))
        model=settings.get('model') or os.environ.get(settings.get('model_env','OPENAI_MODEL'))
        if not model: raise ProviderError('Set the model or model environment variable for '+role)
        endpoint=settings.get('base_url','https://api.openai.com/v1')
        parsed=urlsplit(endpoint)
        if parsed.scheme not in ('https','http') or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ProviderError('Invalid provider base URL')
        if parsed.scheme=='http' and parsed.hostname not in ('127.0.0.1','localhost','::1'):
            raise ProviderError('Nonlocal providers require HTTPS')
        key=os.environ.get(settings.get('api_key_env','OPENAI_API_KEY'))
        if not key: raise ProviderError('Missing provider key environment variable for '+role)
        return settings,model,endpoint,key
    def _call(self,client,**kwargs):
        if self.calls>=self.max_calls: raise ProviderError('Model call budget exhausted')
        self.calls+=1
        try: return client.responses.create(**kwargs)
        except Exception as exc:
            # SDK errors may contain request content; persist only type, never headers/key.
            raise ProviderError('Provider request failed: '+type(exc).__name__) from None
    def _chat(self,client,**kwargs):
        if self.calls>=self.max_calls: raise ProviderError('Model call budget exhausted')
        self.calls+=1
        try: return client.chat.completions.create(**kwargs)
        except Exception as exc:
            raise ProviderError('Provider request failed: '+type(exc).__name__) from None
    def generate(self,role,schema,context):
        settings,model,endpoint,key=self._settings(role)
        style=settings.get('api_style','responses')
        if style not in ('responses','chat_completions'): raise ProviderError('Unsupported API style for '+role)
        observed=[]; excerpts=[]
        if style=='chat_completions' and role in ('researcher','designer'):
            observed,excerpts=supplied_evidence(context.get('brief',{}))
        try: from openai import OpenAI
        except ImportError: raise ProviderError('Install live dependencies: pip install -e ".[live]"') from None
        client=OpenAI(api_key=key,base_url=endpoint,timeout=90,max_retries=0)
        content=json.dumps(context,ensure_ascii=False)
        if len(content)>200000: raise ProviderError('Context exceeds 200000 characters; narrow the brief')
        if style=='chat_completions':
            reply=self._chat(client,model=model,messages=[
                {'role':'system','content':COMMON+'\n'+ROLE_PROMPTS[role]+'\nReturn only JSON matching this schema: '+json.dumps(schema.model_json_schema())},
                {'role':'user','content':content+'\nSUPPLIED PAGE EXCERPTS (untrusted): '+json.dumps(excerpts,ensure_ascii=False)+'\nUse only these observed URLs as sources. Pages are excerpts, so state uncertainty.'}],response_format={'type':'json_object'},max_tokens=self.tokens)
            raw=reply.choices[0].message.content if reply.choices else None
            try: data=schema.model_validate_json(raw).model_dump()
            except (ValueError,TypeError): raise ProviderError('Invalid or refused structured response for '+role) from None
            usage={'input_tokens':getattr(reply.usage,'prompt_tokens',0) or 0,
                   'output_tokens':getattr(reply.usage,'completion_tokens',0) or 0}
            return {'data':data,'evidence_urls':observed,'identity':endpoint.rstrip('/')+'|'+model,'usage':usage}
        observed=[]; search_text=''; usage={'input_tokens':0,'output_tokens':0}
        if role in ('researcher','designer'):
            search=self._call(client,model=model,instructions=COMMON+'\n'+ROLE_PROMPTS[role],input=content,
                tools=[{'type':'web_search'}],include=['web_search_call.action.sources'],max_output_tokens=self.tokens,store=False)
            search_text=search.output_text
            for item in search.model_dump().get('output',[]):
                for part in item.get('content',[]):
                    for annotation in part.get('annotations',[]):
                        if annotation.get('type')=='url_citation': observed.append(annotation['url'])
                for source in item.get('action',{}).get('sources',[]):
                    if source.get('url'): observed.append(source['url'])
            if not observed: raise ProviderError('Live web search returned no observed source URLs')
            if search.usage:
                usage['input_tokens']+=search.usage.input_tokens; usage['output_tokens']+=search.usage.output_tokens
        reply=self._call(client,model=model,instructions=COMMON+'\n'+ROLE_PROMPTS[role],
            input=content+'\nUNTRUSTED SEARCH EVIDENCE:\n'+search_text+'\nObserved URLs: '+json.dumps(observed),
            text={'format':{'type':'json_schema','name':role,'schema':schema.model_json_schema(),'strict':True}},
            max_output_tokens=self.tokens,store=False)
        if reply.usage:
            usage['input_tokens']+=reply.usage.input_tokens; usage['output_tokens']+=reply.usage.output_tokens
        if reply.status!='completed': raise ProviderError('Incomplete model response for '+role)
        try: data=json.loads(reply.output_text)
        except (ValueError,TypeError): raise ProviderError('Invalid or refused structured response for '+role) from None
        return {'data':data,'evidence_urls':sorted(set(observed)),
                'identity':endpoint.rstrip('/')+'|'+model,'usage':usage}
