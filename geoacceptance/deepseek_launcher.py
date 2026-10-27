"""Provider startup with a private local key file; no interactive credential prompt."""
from __future__ import annotations
import argparse,json,os,socket,sys
from pathlib import Path
from .llm import ModelConfig,ModelError

def read_key_file(path,keyvar):
    path=Path(path)
    if not path.exists():return None
    if path.stat().st_size>16384:raise ModelError('Local key file exceeds 16 KiB')
    found=None
    for number,line in enumerate(path.read_text(encoding='utf-8-sig').splitlines(),1):
        line=line.strip()
        if not line or line.startswith('#'):continue
        name,sep,value=line.partition('=')
        if not sep or name.strip()!=keyvar:raise ModelError('Unexpected entry in local key file at line '+str(number))
        if found is not None:raise ModelError('Duplicate key entry in local key file')
        value=value.strip()
        if len(value)>=2 and value[0]==value[-1] and value[0] in ('"',"'"):value=value[1:-1]
        if any(ch.isspace() or ord(ch)<32 for ch in value):raise ModelError('Key must be a single value without whitespace')
        found=value
    return found or None

def main(argv=None,provider='deepseek'):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',action='store_true');p.add_argument('--port',type=int,default=8765);p.add_argument('--data-dir');a=p.parse_args(argv)
    profiles={'deepseek':('https://api.deepseek.com','deepseek-flash','DEEPSEEK_API_KEY','DeepSeek Flash'),
              'qwen':('https://dashscope.aliyuncs.com/compatible-mode/v1','qwen-plus','DASHSCOPE_API_KEY','Qwen Plus Beijing')}
    base,model,keyvar,label=profiles[provider]
    os.environ.update(GA_PROVIDER=provider,GA_BASE_URL=base,GA_MODEL=model,GA_CURRENCY='CNY',GA_THINKING='disabled')
    if provider=='qwen':
        os.environ.pop('GA_API_KEY',None)  # Never reuse another provider's generic key.
        os.environ.update(GA_INPUT_PRICE_PER_MILLION='0.8',GA_OUTPUT_PRICE_PER_MILLION='2',GA_JOB_BUDGET='0.5')
    for k in ('GA_INPUT_USD_PER_MILLION','GA_OUTPUT_USD_PER_MILLION'):os.environ.pop(k,None)
    keyfile=Path(__file__).resolve().parents[1]/'work'/'private'/(provider+'.env')
    try:local_key=read_key_file(keyfile,keyvar)
    except (ModelError,OSError,UnicodeError) as e:
        print(str(e) if isinstance(e,ModelError) else 'Cannot read the local key file',file=sys.stderr);return 2
    if local_key:os.environ[keyvar]=local_key
    cfg=ModelConfig.from_env()
    if a.check:
        print(json.dumps(cfg.public(),ensure_ascii=False));return 0 if cfg.public()['configured'] else 2
    try:cfg.monetary()
    except ModelError as e:print(str(e),file=sys.stderr);return 2
    with socket.socket() as probe:
        if probe.connect_ex(('127.0.0.1',a.port))==0:
            print(f'Port {a.port} is already in use. Close the previous server first; no key has been requested.',file=sys.stderr);return 2
    if not cfg.api_key:
        keyfile.parent.mkdir(parents=True,exist_ok=True)
        if not keyfile.exists():keyfile.write_text('# Local only. Never commit or share this file.\n'+keyvar+'=\n',encoding='utf-8')
        print('Paste your API key after '+keyvar+'= in this local file, save it, then restart:',file=sys.stderr)
        print(str(keyfile),file=sys.stderr);return 2
    from .server import AppServer
    server=None
    try:
        server=AppServer(a.port,a.data_dir)
        print(f'{label} | CNY budget {cfg.monetary()[2]} per job | http://127.0.0.1:{server.server_port}',flush=True)
        print('No model call occurs until you review the outbound preview and request a live draft.',flush=True)
        server.serve_forever()
    except KeyboardInterrupt:pass
    finally:
        if server:server.shutdown();server.server_close();server.service.close()
        if local_key:os.environ.pop(keyvar,None)
    return 0
if __name__=='__main__':raise SystemExit(main())
