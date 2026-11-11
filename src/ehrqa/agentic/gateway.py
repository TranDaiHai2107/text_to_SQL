"""Single-provider model gateway; structured output/usage, no persistent SQL cache."""
from dataclasses import dataclass
import os
import time
import httpx
import math
from .transport import post_json


class ModelError(RuntimeError): pass


@dataclass(frozen=True)
class ModelSettings:
    provider: str
    model: str
    reasoning_effort: str='low'
    deepseek_thinking: bool=False
    request_timeout_s: float=120

    def __post_init__(self):
        if not math.isfinite(self.request_timeout_s) or self.request_timeout_s<=0:
            raise ValueError('Positive finite request deadline required')

    @classmethod
    def from_env(cls):
        from ehrqa.config import BASE_DIR  # loads .env, never calls API
        provider=os.getenv('LLM_PROVIDER','deepseek').lower()
        if provider not in {'deepseek','openai'}:raise ValueError('Unsupported provider')
        model=os.getenv('OPENAI_MODEL','gpt-6-luna') if provider=='openai' else os.getenv('DEEPSEEK_MODEL','deepseek-flash')
        effort=os.getenv('OPENAI_REASONING_EFFORT','low').strip() or 'low'
        return cls(provider,model,effort,os.getenv('DEEPSEEK_THINKING','false').lower()=='true',float(os.getenv('MODEL_REQUEST_TIMEOUT_S','120')))


class Gateway:
    def __init__(self,settings,*,transport=None,budget=None):
        if settings.provider not in {'deepseek','openai'}:raise ValueError('Unsupported provider')
        if not settings.model:raise ValueError('Missing model')
        self.settings=settings
        self.transport=transport
        self.budget=budget

    def complete(self,stage,messages,max_tokens):
        cfg=self.settings
        key=os.getenv(cfg.provider.upper()+'_API_KEY','')
        if not key and self.transport is None:raise ModelError('Missing '+cfg.provider.upper()+'_API_KEY')
        payload={'model':cfg.model,'messages':messages,'stream':False,'response_format':{'type':'json_object'}}
        if cfg.provider=='openai':payload.update(max_completion_tokens=max_tokens,reasoning_effort=cfg.reasoning_effort,service_tier='default')
        else:payload.update(max_tokens=max_tokens,temperature=0,thinking={'type':'enabled' if cfg.deepseek_thinking else 'disabled'})
        url='https://api.openai.com/v1' if cfg.provider=='openai' else 'https://api.deepseek.com'
        started=time.monotonic()
        charge=self.budget.reserve(messages,max_tokens) if self.budget else None
        try:
            response=post_json(url,{'Authorization':'Bearer '+key},payload,
                               timeout_s=cfg.request_timeout_s,transport=self.transport)
            if response.status_code!=200:
                if self.budget:self.budget.finish(charge,status='http_'+str(response.status_code))
                raise ModelError(f'{cfg.provider} HTTP {response.status_code}')
            data=response.json();choice=data['choices'][0]
            if self.budget:self.budget.finish(charge,data.get('usage'))
            content=choice['message'].get('content')
            if choice.get('finish_reason')!='stop' or not isinstance(content,str) or not content.strip():
                raise ModelError('Empty/truncated/incomplete model output')
            return {'content':content,'provider':cfg.provider,'model':data.get('model',cfg.model),
                    'usage':data.get('usage',{}),'service_tier':data.get('service_tier'),
                    'latency_s':round(time.monotonic()-started,4),'finish_reason':'stop'}
        except ModelError:raise
        except (TimeoutError,httpx.TimeoutException):
            raise ModelError('Provider total/inactivity deadline exceeded; request cost may be unknown') from None
        except httpx.TransportError:raise ModelError('Provider transport failed; request cost may be unknown') from None
        except (KeyError,TypeError,ValueError,IndexError):raise ModelError('Malformed provider response') from None
