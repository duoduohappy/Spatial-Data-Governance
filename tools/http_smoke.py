"""Exercise an already-running local app using synthetic input. Creates demo projects."""
import argparse,csv,io,json,re,time,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--url',default='http://127.0.0.1:8765');a=ap.parse_args();base=a.url
    with urllib.request.urlopen(base) as r:page=r.read().decode()
    token=re.search(r'name="csrf" content="([^"]+)"',page).group(1)
    def api(path,data=None):
        req=urllib.request.Request(base+path,json.dumps(data).encode() if data is not None else None,
            {'Content-Type':'application/json','X-CSRF-Token':token} if data is not None else {})
        with urllib.request.urlopen(req) as r:return json.load(r)
    def wait(j):
        for _ in range(400):
            r=api('/api/jobs/'+j['id'])
            if r['status'] not in ('QUEUED','RUNNING'):
                if r['status']!='COMPLETED':raise RuntimeError(r['error'])
                return r
            time.sleep(.025)
        raise RuntimeError('Timeout')
    p=api('/api/examples',{'name':'defective'});pid=p['id']
    wait(api('/api/projects/'+pid+'/draft',{'revision':p['revision'],'key':'http-smoke-draft','mode':'manual'}))
    p=api('/api/projects/'+pid)
    p=api('/api/projects/'+pid+'/approve',{'revision':p['revision'],'proposal':p['draft'],'reviewer':'自动化示例校验（非真实用户审核）'})
    j=wait(api('/api/projects/'+pid+'/validate',{'revision':p['revision'],'key':'http-smoke-run'}))
    assert j['result']['aggregate_verdict']=='FAIL'
    with urllib.request.urlopen(base+'/api/jobs/'+j['id']+'/report.html') as r:assert 'text/html' in r.headers['Content-Type']
    q=api('/api/projects/'+pid+'/corrected',{'revision':p['revision'],'name':'示例 · 整改批次',
        'files':{'poi.csv':(ROOT/'examples'/'corrected'/'poi.csv').read_text(encoding='utf-8')}})
    k=wait(api('/api/projects/'+q['id']+'/validate',{'revision':q['revision'],'key':'http-smoke-corrected'}))
    assert k['result']['aggregate_verdict']=='PASS'
    compare=api('/api/compare',{'before':j['id'],'after':k['id']})
    assert compare['overall']=='LEDGER_INDETERMINATE' # original duplicated ID cannot be magically resolved
    evidence={'status':'PASS','mode':'manual','live_model_calls':0,'before_project':pid,'after_project':q['id'],
       'before_verdict':j['result']['aggregate_verdict'],'after_verdict':k['result']['aggregate_verdict'],
       'compare_overall':compare['overall'],'compare_counts':compare['counts'],'api_sequence':['create','draft','approve','validate','export HTML','corrected','validate','compare']}
    (ROOT/'acceptance'/'stage-3'/'http-e2e.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(evidence,ensure_ascii=False))
if __name__=='__main__':main()
