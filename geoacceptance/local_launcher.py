"""Start a local-only Ollama runtime and an isolated GeoAcceptance workspace."""
from __future__ import annotations
import argparse,json,os,socket,subprocess,sys,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def local_env(root):
    env=os.environ.copy()
    for k in list(env):
        if k.startswith('GA_') or k in ('DASHSCOPE_API_KEY','DEEPSEEK_API_KEY','OPENAI_API_KEY','OLLAMA_API_KEY'):
            env.pop(k,None)
    for n in ('profile','models','tmp'):(root/n).mkdir(parents=True,exist_ok=True)
    env.update(USERPROFILE=str(root/'profile'),OLLAMA_MODELS=str(root/'models'),OLLAMA_HOST='127.0.0.1:11434',
        OLLAMA_NO_CLOUD='1',OLLAMA_NUM_PARALLEL='1',OLLAMA_MAX_LOADED_MODELS='1',OLLAMA_MAX_QUEUE='2',
        OLLAMA_CONTEXT_LENGTH='8192',OLLAMA_KEEP_ALIVE='60s',OLLAMA_FLASH_ATTENTION='1',OLLAMA_KV_CACHE_TYPE='q8_0',
        TEMP=str(root/'tmp'),TMP=str(root/'tmp'),NO_PROXY='localhost,127.0.0.1,::1')
    return env

def port_in_use(port):
    with socket.socket() as sock:return sock.connect_ex(('127.0.0.1',port))==0

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--port',type=int,default=8766);a=p.parse_args(argv)
    runtime=ROOT/'work/local-model';exe=runtime/'ollama/ollama.exe'
    if not exe.exists():print('Portable Ollama is not installed; see docs/LOCAL_MODEL.md',file=sys.stderr);return 2
    if port_in_use(a.port):print('Workbench port is already in use; existing services left untouched.',file=sys.stderr);return 2
    env=local_env(runtime);owned=None;log=None
    local_http=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        if not port_in_use(11434):
            log=(runtime/'server.log').open('ab')
            owned=subprocess.Popen([str(exe),'serve'],env=env,stdout=log,stderr=log,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        ready=False
        for _ in range(100):
            if owned and owned.poll() is not None:print('Ollama stopped; inspect work/local-model/server.log',file=sys.stderr);return 2
            try:
                with local_http.open('http://127.0.0.1:11434/api/version',timeout=1) as r:version=json.load(r)
                ready=True;break
            except OSError as error:
                if isinstance(getattr(error,'reason',None),PermissionError):
                    print('Local network permission denied; restore sandbox network access (WinError 10013).',file=sys.stderr);return 2
                time.sleep(.2)
        if not ready:print('Local model server startup timed out',file=sys.stderr);return 2
        with local_http.open('http://127.0.0.1:11434/api/tags',timeout=5) as r:models=json.load(r)['models']
        model=next((m for m in models if m.get('name')=='geoacceptance-qwen3:4b'),None)
        if not model or model.get('remote_host') or model.get('remote_model'):
            print('Expected local model is missing or remote; see docs/LOCAL_MODEL.md',file=sys.stderr);return 2
        app_env={k:v for k,v in env.items() if not k.startswith('OLLAMA_')}
        app_env.update(GA_PROVIDER='ollama',GA_BASE_URL='http://127.0.0.1:11434/v1',GA_MODEL='geoacceptance-qwen3:4b',
                       GA_TIMEOUT_SECONDS='300',GA_MAX_CALLS='1',GA_INPUT_PRICE_PER_MILLION='0',
                       GA_OUTPUT_PRICE_PER_MILLION='0',GA_JOB_BUDGET='0',GA_CURRENCY='CNY')
        os.environ.clear();os.environ.update(app_env)
        from .server import AppServer
        app=AppServer(a.port,ROOT/'work/local-app')
        print(f'LOCAL Qwen3 4B | no cloud API charge | http://127.0.0.1:{a.port}',flush=True)
        print('Local projects use work/local-app; existing cloud workspace is preserved.',flush=True)
        try:app.serve_forever()
        except KeyboardInterrupt:pass
        finally:app.shutdown();app.server_close();app.service.close()
    finally:
        if owned and owned.poll() is None:owned.terminate();owned.wait(timeout=20)
        if log:log.close()
    return 0
if __name__=='__main__':raise SystemExit(main())
