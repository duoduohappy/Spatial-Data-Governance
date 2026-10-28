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
    scoped=api('/api/examples',{'name':'scoped_sources'})
    scoped_draft=wait(api('/api/projects/'+scoped['id']+'/draft',{'revision':scoped['revision'],'key':'scope-draft','mode':'manual'}))
    detail=api('/api/projects/'+scoped['id'])
    scoped=api('/api/projects/'+scoped['id']+'/approve',{'revision':detail['revision'],'proposal':detail['draft'],'reviewer':'CI synthetic scope review; not independent user approval'})
    scoped_run=wait(api('/api/projects/'+scoped['id']+'/validate',{'revision':scoped['revision'],'key':'scope-pass'}))
    assert scoped_run['result']['aggregate_verdict']=='PASS'
    instances=[r for r in scoped_run['result']['check_results'] if r.get('scope')]
    assert len(instances)==2 and all(r['summary_counts']['records_evaluated']==1 for r in instances)
    checks.append('two independent source-scoped freshness instances PASS')
    text=(ROOT/'examples/scoped_sources/poi.csv').read_text(encoding='utf-8');reader=csv.DictReader(io.StringIO(text));fields=reader.fieldnames;rows=list(reader)
    rows.append(dict(rows[0],record_id='M-002',name='Another synthetic municipal facility'))
    rows[0]['source_time']='2026-09-10T00:00:00Z'
    def scoped_correction(parent,records,name):
        buffer=io.StringIO();writer=csv.DictWriter(buffer,fieldnames=fields);writer.writeheader();writer.writerows(records)
        return api('/api/projects/'+parent['id']+'/corrected',{'revision':parent['revision'],'files':{'poi.csv':buffer.getvalue()},'name':name})
    stale_scope=scoped_correction(scoped,rows,'scope stale')
    scope_before=wait(api('/api/projects/'+stale_scope['id']+'/validate',{'revision':stale_scope['revision'],'key':'scope-stale'}))
    assert scope_before['result']['aggregate_verdict']=='FAIL'
    failed=[r for r in scope_before['result']['check_results'] if r.get('scope') and r['verdict']=='FAIL']
    assert len(failed)==1 and failed[0]['scope']['equals']=='municipal'
    checks.append('seven-day rule does not misapply to thirty-day source')
    rows[0]['source']='survey';moved=scoped_correction(stale_scope,rows,'scope moved')
    scope_after=wait(api('/api/projects/'+moved['id']+'/validate',{'revision':moved['revision'],'key':'scope-moved'}))
    assert scope_after['result']['aggregate_verdict']=='PASS'
    ledger=api('/api/compare',{'before':scope_before['id'],'after':scope_after['id']})
    assert ledger['overall']=='LEDGER_INDETERMINATE'
    assert not any(i.get('record_id')=='M-001' and i['status']=='closed' for i in ledger['items'])
    checks.append('moving source cannot falsely close an original failure')
    with urllib.request.urlopen(base+'/api/jobs/'+scoped_run['id']+'/report.html',timeout=10) as response:
        assert 'source=municipal' in response.read().decode()
    checks.append('HTML report retains explicit source scope')
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
