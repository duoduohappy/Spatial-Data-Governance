"""Bounded compatible client with an explicit DeepSeek preset. Credentials stay in memory."""
from __future__ import annotations
import json,os,time,math,re,urllib.request,urllib.error,urllib.parse
from dataclasses import dataclass

class ModelError(ValueError):
    def __init__(self,message,*,code='MODEL_ERROR',http_status=None,provider_code=None,retryable=True):
        super().__init__(message);self.code=code;self.http_status=http_status;self.provider_code=provider_code;self.retryable=retryable

@dataclass
class ModelConfig:
    base_url:str=''
    model:str=''
    api_key:str=''
    timeout:int=45
    max_output_tokens:int=3500
    max_calls:int=2
    max_input_chars:int=50000
    budget_usd:float=0.10
    input_usd_per_million:float|None=None
    output_usd_per_million:float|None=None
    provider:str='compatible'
    currency:str='USD'
    input_price_per_million:float|None=None
    output_price_per_million:float|None=None
    job_budget:float|None=None
    thinking:str='disabled'

    @classmethod
    def from_env(cls):
        def rate(k):return float(os.environ[k]) if os.getenv(k) else None
        profiles={
            'compatible':('', '', '', 'USD',None,None,None),
            'deepseek':('https://api.deepseek.com','deepseek-flash','DEEPSEEK_API_KEY','CNY',2.0,8.0,0.5),
            'qwen':('https://dashscope.aliyuncs.com/compatible-mode/v1','qwen-plus','DASHSCOPE_API_KEY','CNY',0.8,2.0,0.5),
            'ollama':('http://127.0.0.1:11434/v1','geoacceptance-qwen3:4b','','CNY',0.0,0.0,0.0)}
        provider=os.getenv('GA_PROVIDER') or 'compatible'
        if provider not in profiles:raise ModelError('Unknown GA_PROVIDER; use compatible, deepseek, qwen or ollama')
        base,model,keyvar,currency,inp,out,budget=profiles[provider];preset=provider!='compatible'
        return cls(base_url=os.getenv('GA_BASE_URL') or base,model=os.getenv('GA_MODEL') or model,
            api_key='' if provider=='ollama' else ((os.getenv(keyvar,'') if keyvar else '') or os.getenv('GA_API_KEY','')),
            timeout=int(os.getenv('GA_TIMEOUT_SECONDS','300' if provider=='ollama' else '90' if preset else '45')),
            max_output_tokens=int(os.getenv('GA_MAX_OUTPUT_TOKENS','8192' if preset else '3500')),
            max_calls=int(os.getenv('GA_MAX_CALLS','1' if provider=='ollama' else '2')),max_input_chars=int(os.getenv('GA_MAX_INPUT_CHARS','50000')),
            budget_usd=float(os.getenv('GA_JOB_BUDGET_USD','0.10')),
            input_usd_per_million=rate('GA_INPUT_USD_PER_MILLION'),output_usd_per_million=rate('GA_OUTPUT_USD_PER_MILLION'),
            provider=provider,currency=os.getenv('GA_CURRENCY') or currency,
            input_price_per_million=rate('GA_INPUT_PRICE_PER_MILLION') if os.getenv('GA_INPUT_PRICE_PER_MILLION') else inp,
            output_price_per_million=rate('GA_OUTPUT_PRICE_PER_MILLION') if os.getenv('GA_OUTPUT_PRICE_PER_MILLION') else out,
            job_budget=rate('GA_JOB_BUDGET') if os.getenv('GA_JOB_BUDGET') else budget,
            thinking=os.getenv('GA_THINKING') or 'disabled')

    def monetary(self):
        if self.provider in ('deepseek','qwen') and self.currency!='CNY':raise ModelError('Provider preset uses CNY; use compatible profile for other billing currencies')
        if self.currency not in ('USD','CNY'):raise ModelError('Currency must be USD or CNY')
        if self.currency!='USD' and any(v is not None for v in (self.input_usd_per_million,self.output_usd_per_million)):
            raise ModelError('Do not mix USD legacy rates with a non-USD currency')
        prices=(self.input_price_per_million if self.input_price_per_million is not None else self.input_usd_per_million,
                self.output_price_per_million if self.output_price_per_million is not None else self.output_usd_per_million)
        budget=self.job_budget if self.job_budget is not None else (self.budget_usd if self.currency=='USD' else None)
        if any(v is None for v in (*prices,budget)):raise ModelError('Set input/output prices and job budget in the selected currency')
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in (*prices,budget)):
            raise ModelError('Price/budget must be finite non-negative numbers')
        return (*prices,budget)

    def public(self):
        u=urllib.parse.urlsplit(self.base_url)
        try:self.monetary();priced=True
        except ModelError:priced=False
        endpoint=bool(self.base_url and self.model)
        key_ok=bool(self.api_key) or (self.provider!='deepseek' and u.hostname in ('localhost','127.0.0.1','::1'))
        return {'configured':endpoint and key_ok and priced,'endpoint_configured':endpoint,'provider':self.provider,
            'model':self.model,'endpoint_origin':f'{u.scheme}://{u.hostname or ""}' if self.base_url else '',
            'key_present':bool(self.api_key),'pricing_configured':priced,'currency':self.currency,
            'thinking':self.thinking if self.provider in ('deepseek','qwen','ollama') else None}

class CompatibleClient:
    def __init__(self,config=None,transport=None):
        self.config=config or ModelConfig.from_env();self.transport=transport or self._http;self.calls=[]
    def _http(self,payload):
        c=self.config;u=urllib.parse.urlsplit(c.base_url)
        if u.username or u.password or u.query or u.fragment:raise ModelError('Endpoint must not contain credentials/query/fragment')
        if u.scheme!='https' and not(u.scheme=='http' and u.hostname in ('localhost','127.0.0.1','::1')):
            raise ModelError('Use HTTPS, or HTTP on loopback for a local model')
        req=urllib.request.Request(c.base_url.rstrip('/')+'/chat/completions',json.dumps(payload).encode(),
            {'Content-Type':'application/json',**({'Authorization':'Bearer '+c.api_key} if c.api_key else {})})
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,*args):return None
        try:
            handlers=[NoRedirect()]
            if u.hostname in ('localhost','127.0.0.1','::1'):handlers.append(urllib.request.ProxyHandler({}))
            with urllib.request.build_opener(*handlers).open(req,timeout=c.timeout) as r:
                data=r.read(2_000_001)
                if len(data)>2_000_000:raise ModelError('Model response exceeded limit')
                return json.loads(data)
        except urllib.error.HTTPError as e:
            provider_code=None
            try:
                body=json.loads(e.read(65536));error=body.get('error',{})
                candidate=(error.get('code') if isinstance(error,dict) else None) or body.get('code')
                if (isinstance(candidate,str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,79}',candidate)
                    and not candidate.startswith(('sk-','ghp_')) and (not c.api_key or c.api_key not in candidate)):
                    provider_code=candidate
            except (ValueError,TypeError,AttributeError,OSError):pass
            finally:e.close()
            raise ModelError('Provider HTTP '+str(e.code),code='PROVIDER_HTTP_ERROR',http_status=e.code,
                provider_code=provider_code,retryable=(e.code==429 or e.code>=500)) from None
        except (urllib.error.URLError,TimeoutError,OSError) as e:
            code='PROVIDER_TIMEOUT' if isinstance(e,TimeoutError) else 'PROVIDER_NETWORK_ERROR'
            raise ModelError('Provider unavailable or timeout',code=code) from None
    def complete(self,messages,response_schema=None):
        c=self.config
        if not 1<=c.max_calls<=3 or not 1<=c.timeout<=(600 if c.provider=='ollama' else 120) or not 1<=c.max_output_tokens<=16000 or not 1<=c.max_input_chars<=100000:
            raise ModelError('Call/token/time limits outside safe bounds')
        if not c.base_url or not c.model:raise ModelError('Configure GA_BASE_URL and GA_MODEL; real model not configured')
        if c.provider=='ollama':
            u=urllib.parse.urlsplit(c.base_url)
            if u.scheme!='http' or u.netloc not in ('127.0.0.1:11434','localhost:11434','[::1]:11434') or u.path.rstrip('/')!='/v1' or u.query or u.fragment or c.api_key:
                raise ModelError('Local Ollama preset only uses loopback port 11434 without credentials')
            if c.model!='geoacceptance-qwen3:4b' or c.thinking!='disabled':
                raise ModelError('Local preset uses the installed local-only model with thinking disabled')
            if any(c.monetary()):raise ModelError('Local preset uses zero cloud API pricing')
        if c.provider=='deepseek':
            if c.model!='deepseek-flash':raise ModelError('DeepSeek preset rates are for deepseek-flash only; use compatible profile for other models')
            u=urllib.parse.urlsplit(c.base_url)
            if u.scheme!='https' or u.netloc!='api.deepseek.com' or u.path not in ('','/','/v1','/v1/') or u.query or u.fragment:
                raise ModelError('DeepSeek preset only sends credentials to https://api.deepseek.com')
            if not c.api_key:raise ModelError('Set DEEPSEEK_API_KEY or GA_API_KEY locally; do not send the key in chat')
            if c.thinking not in ('enabled','disabled'):raise ModelError('GA_THINKING must be enabled or disabled')
        if c.provider=='qwen':
            u=urllib.parse.urlsplit(c.base_url)
            if u.scheme!='https' or u.netloc!='dashscope.aliyuncs.com' or u.path.rstrip('/')!='/compatible-mode/v1' or u.query or u.fragment:
                raise ModelError('Qwen Beijing preset only sends credentials to https://dashscope.aliyuncs.com/compatible-mode/v1')
            if c.model not in ('qwen-plus','qwen-plus-2025-12-01') or c.thinking!='disabled':
                raise ModelError('Qwen preset requires qwen-plus with thinking disabled; other models/modes need explicit compatible-profile pricing')
            if not c.api_key:raise ModelError('Set DASHSCOPE_API_KEY locally; do not send the key in chat')
            if sum(len(m['content'].encode('utf-8'))+64 for m in messages)>120000:
                raise ModelError('Qwen preset input bound exceeded; remain below the 128K input pricing tier')
        if sum(len(m.get('content','')) for m in messages)>c.max_input_chars:raise ModelError('Input text budget exceeded')
        in_rate,out_rate,budget=c.monetary()
        reserve=(sum(len(m['content'].encode('utf-8'))+64 for m in messages)*in_rate+c.max_output_tokens*out_rate)/1e6
        spent=0
        for attempt in range(c.max_calls):
            if spent+reserve>budget:raise ModelError('Cost reservation exceeds job budget')
            spent+=reserve
            start=time.perf_counter();record={'attempt':attempt+1,'model':c.model,'currency':c.currency,
                'reserved_cost':reserve,'reserved_usd':reserve if c.currency=='USD' else None,'usage':None,
                'cost':None,'cost_usd':None,'cost_basis':'estimate at configured rates; not provider invoice','status':'ERROR'}
            try:
                payload={'model':c.model,'messages':messages,'temperature':0,'max_tokens':c.max_output_tokens,'response_format':{'type':'json_object'}}
                if c.provider=='deepseek':payload['thinking']={'type':c.thinking}
                if c.provider=='qwen':payload['enable_thinking']=False
                if c.provider=='ollama':
                    payload['reasoning_effort']='none'
                    if response_schema is not None:payload['response_format']={'type':'json_schema','json_schema':{'name':'geoacceptance_draft','schema':response_schema}}
                r=self.transport(payload);usage=r.get('usage')
                if isinstance(usage,dict):
                    keys=('prompt_tokens','completion_tokens','total_tokens')
                    record['usage']={k:usage.get(k) if type(usage.get(k)) is int and usage[k]>=0 else None for k in keys}
                    if all(type(usage.get(k)) is int and usage[k]>=0 for k in keys[:2]):
                        record['cost']=(usage['prompt_tokens']*in_rate+usage['completion_tokens']*out_rate)/1e6
                        if c.currency=='USD':record['cost_usd']=record['cost']
                choice=r['choices'][0]
                if choice.get('finish_reason')=='length':raise ModelError('Model output truncated; increase output budget after review')
                obj=json.loads(choice['message']['content'])
                if not isinstance(obj,dict):raise ModelError('Expected JSON object')
                record['status']='OK';return obj
            except (ValueError,KeyError,IndexError,TypeError,ModelError) as e:
                record['error']=type(e).__name__
                if isinstance(e,ModelError):
                    record.update(error_code=e.code,http_status=e.http_status,provider_code=e.provider_code)
                    if not e.retryable:
                        raise ModelError('Provider HTTP '+str(e.http_status)+((' ('+e.provider_code+')') if e.provider_code else '')+'; check request parameters, key, region and account permissions',code=e.code,http_status=e.http_status,provider_code=e.provider_code,retryable=False) from None
                if attempt+1==c.max_calls:raise ModelError('Model failed after bounded attempts; see call metadata') from None
            finally:
                record['duration_ms']=round((time.perf_counter()-start)*1000,2);self.calls.append(record)
        raise ModelError('No response')
