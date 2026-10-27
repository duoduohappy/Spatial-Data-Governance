"""Exercise an already running workbench through HTTP. Synthetic manual mode only; no model calls."""
from __future__ import annotations
import argparse,json,re,time,urllib.request,urllib.error,datetime,csv,io
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def run(base):
    if not re.fullmatch(r'http://(?:127\.0\.0\.1|localhost):\d+',base):raise ValueError('Use a loopback test endpoint')
    with urllib.request.urlopen(base,timeout=10) as r:
        token=re.search(r'name="csrf" content="([^"]+)"',r.read().decode()).group(1)
    def api(path,data=None):
        req=urllib.request.Request(base+path,json.dumps(data,ensure_ascii=False).encode() if data is not None else None,
            {'Content-Type':'application/json','X-CSRF-Token':token})
        with urllib.request.urlopen(req,timeout=15) as r:return json.load(r)
    def wait(job):
        for _ in range(300):
            value=api('/api/jobs/'+job['id'])
            if value['status'] not in ('RUNNING','QUEUED'):
                assert value['status']=='COMPLETED',value.get('error');return value
            time.sleep(.1)
        raise RuntimeError('Job timeout')
    checks=[]
    try:
        urllib.request.urlopen(urllib.request.Request(base+'/api/examples',b'{"name":"clean"}',{'Content-Type':'application/json'}),timeout=10)
        raise AssertionError('CSRF bypass')
    except urllib.error.HTTPError as error:assert error.code==403
    checks.append('CSRF rejection')
    project=api('/api/examples',{'name':'clean'})
    draft=wait(api('/api/projects/'+project['id']+'/draft',{'revision':project['revision'],'key':'http-probe-manual','mode':'manual'}))
    assert draft['result']['mode']=='manual' and draft['result']['calls']==[]
    detail=api('/api/projects/'+project['id']);assert detail['approval'] is None
    checks.append('draft remains unapproved; zero model calls')
    project=api('/api/projects/'+project['id']+'/approve',{'revision':detail['revision'],'proposal':detail['draft'],'reviewer':'CI synthetic scripted review; not user approval'})
    clean=wait(api('/api/projects/'+project['id']+'/validate',{'revision':project['revision'],'key':'http-probe-clean'}))
    assert clean['result']['aggregate_verdict']=='PASS';checks.append('clean PASS')
    def correction(parent,example):
        return api('/api/projects/'+parent['id']+'/corrected',{'revision':parent['revision'],
            'files':{'poi.csv':(ROOT/'examples'/example/'poi.csv').read_text(encoding='utf-8')},'name':'HTTP probe '+example})
    bad=correction(project,'defective');before=wait(api('/api/projects/'+bad['id']+'/validate',{'revision':bad['revision'],'key':'http-probe-bad'}))
    assert before['result']['aggregate_verdict']=='FAIL';checks.append('defective FAIL')
    fixed=correction(bad,'corrected');after=wait(api('/api/projects/'+fixed['id']+'/validate',{'revision':fixed['revision'],'key':'http-probe-fixed'}))
    assert after['result']['aggregate_verdict']=='PASS';checks.append('corrected PASS')
    comparison=api('/api/compare',{'before':before['id'],'after':after['id']})
    assert comparison['overall']=='LEDGER_INDETERMINATE' and comparison['counts'].get('closed',0)>0,comparison
    checks.append('duplicate identity prevents false closure despite corrected batch PASS')
    # Independent positive closure: one stale record, stable unique identities, same approved ruler.
    original=(ROOT/'examples/clean/poi.csv').read_text(encoding='utf-8');reader=csv.DictReader(io.StringIO(original));fields=reader.fieldnames;rows=list(reader)
    rows[0]['source_time']='2000-01-01T00:00:00Z'
    stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    single=api('/api/projects/'+project['id']+'/corrected',{'revision':project['revision'],'files':{'poi.csv':stream.getvalue()},'name':'HTTP probe single stale record'})
    stale=wait(api('/api/projects/'+single['id']+'/validate',{'revision':single['revision'],'key':'http-probe-stale'}))
    assert stale['result']['aggregate_verdict']=='FAIL'
    restored=api('/api/projects/'+single['id']+'/corrected',{'revision':single['revision'],'files':{'poi.csv':original},'name':'HTTP probe restored'})
    restored_job=wait(api('/api/projects/'+restored['id']+'/validate',{'revision':restored['revision'],'key':'http-probe-restored'}))
    positive=api('/api/compare',{'before':stale['id'],'after':restored_job['id']})
    assert positive['overall']=='LEDGER_CLOSED_ACCEPTED',positive
    checks.append('positive closure with stable identity and successful rule execution')
    for kind in ('json','html'):
        with urllib.request.urlopen(base+'/api/jobs/'+after['id']+'/report.'+kind,timeout=10) as response:
            assert 'attachment' in response.headers.get('Content-Disposition','')
            body=response.read().decode()
            assert json.loads(body)['aggregate_verdict']=='PASS' if kind=='json' else '<html' in body
        checks.append(kind+' export body and attachment headers')
    return {'status':'PASS','at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'base':base,'checks':checks,
        'mode':'manual synthetic workflow; zero model calls','scope':'HTTP workflow probe; environment/container provenance must be supplied separately.'}

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--base',default='http://127.0.0.1:8765');parser.add_argument('--out',required=True);args=parser.parse_args()
    result=run(args.base);path=Path(args.out);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
