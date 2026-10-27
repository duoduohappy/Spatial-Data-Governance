from pathlib import Path
import sys,tempfile,time,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from geoacceptance.service import Service
from geoacceptance.authoring import create_draft

def wait(s,j):
    for _ in range(1000):
        r=s.job(j['id'])
        if r['status'] not in ('QUEUED','RUNNING'):return r
        time.sleep(.01)
    raise RuntimeError('Timeout')
if __name__=='__main__':
    root=Path(__file__).resolve().parents[1]
    s=Service(root/'work'/'first-smoke')
    p=s.example('defective');print('PROJECT',p['id'])
    j=wait(s,s.submit(p['id'],'draft',p['revision'],'draft'))
    print('DRAFT',j['status'],j['error'])
    if j['status']!='COMPLETED':raise RuntimeError(j['error'])
    p=s.detail(p['id']);print('COUNTS',len(p['draft']['requirements']),len(p['draft']['rules']))
    p=s.approve(p['id'],p['revision'],p['draft'],'smoke-reviewer');print('APPROVED',p['revision'])
    j=wait(s,s.submit(p['id'],'validate',p['revision'],'validate'));print('VALIDATE',j['status'],j['error'],(j['result'] or {}).get('aggregate_verdict'))
    s.close()

