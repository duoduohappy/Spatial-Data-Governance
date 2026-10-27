"""Install pinned portable Ollama and Qwen3 4B under work/; no cloud API or system installation."""
from __future__ import annotations
import argparse,hashlib,json,os,shutil,subprocess,sys,time,urllib.request,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from geoacceptance.local_launcher import local_env,port_in_use
ROOT=Path(__file__).resolve().parents[1]
VERSION='v0.40.11'
SHA256='bda4a493ba8a7c24d57263cd843cd68cee84f44aed4299eeed532acad7eda12a'
URL=f'https://github.com/ollama/ollama/releases/download/{VERSION}/ollama-windows-amd64.zip'

def api(path,data=None):
    req=urllib.request.Request('http://127.0.0.1:11434'+path,json.dumps(data).encode() if data is not None else None,
        {'Content-Type':'application/json'} if data is not None else {})
    with urllib.request.urlopen(req,timeout=120) as r:return json.load(r)

def main():
    if os.name!='nt':raise SystemExit('This portable installer is for Windows; install Ollama for your OS separately.')
    root=ROOT/'work/local-model';root.mkdir(parents=True,exist_ok=True)
    if shutil.disk_usage(root).free<12*2**30:raise SystemExit('Keep at least 12 GiB free for runtime, model and temporary download.')
    archive=root/'ollama-windows-amd64.zip'
    if not archive.exists():
        tmp=archive.with_suffix('.part');done=0;last=0
        with urllib.request.urlopen(urllib.request.Request(URL,headers={'User-Agent':'GeoAcceptance-local-setup'}),timeout=60) as r,tmp.open('wb') as f:
            total=int(r.headers.get('Content-Length','0'))
            while chunk:=r.read(4*1024*1024):
                f.write(chunk);done+=len(chunk)
                if time.monotonic()-last>10:
                    print(f'Ollama download: {done//2**20} MiB / {total//2**20} MiB',flush=True);last=time.monotonic()
        with tmp.open('rb') as f:
            if hashlib.file_digest(f,'sha256').hexdigest()!=SHA256:raise RuntimeError('Ollama digest mismatch; refusing installation')
        tmp.replace(archive)
    with archive.open('rb') as f:
        if hashlib.file_digest(f,'sha256').hexdigest()!=SHA256:raise RuntimeError('Ollama digest mismatch')
    target=root/'ollama';target.mkdir(exist_ok=True)
    if not (target/'ollama.exe').exists():
        with zipfile.ZipFile(archive) as z:
            if any(not (target/i.filename).resolve().is_relative_to(target) for i in z.infolist()):raise RuntimeError('Unsafe archive path')
            z.extractall(target)
    env=local_env(root);process=None;log=None
    try:
        if not port_in_use(11434):
            log=(root/'server.log').open('ab')
            process=subprocess.Popen([str(target/'ollama.exe'),'serve'],env=env,stdout=log,stderr=log,creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(100):
            try:version=api('/api/version');break
            except OSError:
                if process and process.poll() is not None:raise RuntimeError('Ollama exited; inspect local server.log')
                time.sleep(.2)
        else:raise RuntimeError('Ollama startup timeout')
        req=urllib.request.Request('http://127.0.0.1:11434/api/pull',json.dumps({'model':'qwen3:4b','stream':True}).encode(),{'Content-Type':'application/json'})
        last=0
        with urllib.request.urlopen(req,timeout=120) as r:
            for line in r:
                d=json.loads(line)
                if d.get('error'):raise RuntimeError('Model pull failed')
                if d.get('total') and time.monotonic()-last>10:
                    print('Qwen download: '+str(round(d.get('completed',0)/d['total']*100,1))+'%',flush=True);last=time.monotonic()
        result=api('/api/create',{'model':'geoacceptance-qwen3:4b','from':'qwen3:4b',
            'parameters':{'num_ctx':16384,'num_predict':8192,'temperature':0},'stream':False})
        if result.get('status')!='success':raise RuntimeError('Local model alias creation failed')
        proof={'ollama':version,'source':URL,'sha256':SHA256,'verified':True,'models':api('/api/tags')['models'],'mode':'local-only weights; no API key'}
        (root/'setup-proof.json').write_text(json.dumps(proof,indent=2),encoding='utf-8')
        print('Ready. Run start-local.cmd and open http://127.0.0.1:8766',flush=True)
    finally:
        if process and process.poll() is None:process.terminate();process.wait(timeout=20)
        if log:log.close()
if __name__=='__main__':main()
