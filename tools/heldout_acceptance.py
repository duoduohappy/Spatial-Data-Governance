"""Evaluate a pre-frozen developer-labelled holdout using the production local authoring path."""
from __future__ import annotations
import json,hashlib,datetime,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from geoacceptance.authoring import create_draft,SYSTEM
from geoacceptance.local_authoring import GUIDANCE
from geoacceptance.llm import ModelConfig,CompatibleClient
from tools.live_acceptance import source_validation,outbound_preview

def parameters_match(actual,expected):
    if not isinstance(actual,dict):return False
    return all(set(actual.get(k,[]))==set(v) if k=='fields' else actual.get(k)==v for k,v in expected.items())

def score(case,draft):
    raw=draft.get('model_proposal',{});raw_reqs=raw.get('requirements',[]);raw_rules=raw.get('rules',[])
    compiled_reqs=draft['requirements'];compiled_rules=draft['rules'];rows=[]
    for truth in case['truth']:
        quote=truth['source_quote'];typ=truth['rule_type']
        def check(reqs,rules):
            matched=[q for q in reqs if q.get('source_quote')==quote]
            if len(matched)!=1:return False
            q=matched[0];bound=[r for r in rules if r.get('rule_type')==typ and r.get('requirement_ids')==[q['requirement_id']]]
            if not truth['supported']:
                # Retaining a bound usable-looking rule is not correct abstention.
                return q.get('support_status')!='SUPPORTED' and not bound and q.get('required_for_release') is True
            if q.get('support_status')!='SUPPORTED' or q.get('required_for_release')==truth['advisory'] or len(bound)!=1:return False
            return parameters_match(bound[0].get('parameters'),truth['parameters'])
        rows.append({'quote':quote,'rule_type':typ,'expected_supported':truth['supported'],
            'raw_semantics_correct':check(raw_reqs,raw_rules),'compiled_semantics_correct':check(compiled_reqs,compiled_rules),
            'covered':any(q.get('source_quote')==quote for q in compiled_reqs)})
    return rows

def main():
    dataset=ROOT/'eval/heldout-v1';manifest_path=dataset/'manifest.json';manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
    digest=hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if hashlib.sha256((SYSTEM+GUIDANCE).encode()).hexdigest()!=manifest['prompt_sha256']:raise RuntimeError('Prompt changed after holdout freeze; label the set exposed before retuning')
    for key in list(os.environ):
        if key.startswith('GA_') or key in ('DASHSCOPE_API_KEY','DEEPSEEK_API_KEY','OPENAI_API_KEY'):os.environ.pop(key,None)
    os.environ.update(GA_PROVIDER='ollama',GA_MAX_CALLS='1',GA_TIMEOUT_SECONDS='300')
    out=ROOT/'acceptance/stage-4/local-model/heldout-v1';out.mkdir(parents=True,exist_ok=True);target=out/'results.json'
    report=json.loads(target.read_text(encoding='utf-8')) if target.exists() else {'status':'RUNNING','manifest_sha256':digest,'cases':[],
        'scope':manifest['scope'],'provenance':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['geoacceptance/authoring.py','geoacceptance/local_authoring.py','geoacceptance/llm.py','tools/heldout_acceptance.py']},
        'criteria':{'compiled_complete_rule_mapping_min':0.90,'clause_coverage_min':1.0,'parameter_lineage_problems_max':0,'automatic_approvals_max':0,'unknown_clause_errors_max':0},
        'at':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    assert report['manifest_sha256']==digest
    done={c['id'] for c in report['cases']}
    def save():target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    for case in manifest['cases']:
        if case['id'] in done:continue
        bundle=dataset/case['id'];assert hashlib.sha256((bundle/'delivery_spec.md').read_bytes()).hexdigest()==case['document_sha256']
        (out/(case['id']+'-preview.json')).write_text(json.dumps(outbound_preview(bundle),ensure_ascii=False,indent=2),encoding='utf-8')
        client=CompatibleClient(ModelConfig.from_env());row={'id':case['id'],'human_review':'NOT_REVIEWED','status':'RUNNING'};start=time.perf_counter()
        try:
            draft=create_draft(bundle,'live',client);row['draft']=draft;row['scores']=score(case,draft);row['source_validation']=source_validation(bundle,draft)
            row['draft_only']=all(r['status']=='DRAFT' and not r['reviewer'] for r in draft['rules']);row['status']='MEASURED'
        except (ValueError,TypeError,KeyError) as error:row.update(status='FAILED',error_type=type(error).__name__,error=str(error)[:1000])
        row.update(calls=client.calls,duration_ms=round((time.perf_counter()-start)*1000,2));report['cases'].append(row);save()
        print(json.dumps({'id':case['id'],'status':row['status'],'compiled_correct':sum(s['compiled_semantics_correct'] for s in row.get('scores',[])),'raw_correct':sum(s['raw_semantics_correct'] for s in row.get('scores',[]))}),flush=True)
    scores=[s for c in report['cases'] for s in c.get('scores',[])];total=sum(len(c['truth']) for c in manifest['cases'])
    metrics={'clauses':total,'raw_semantics_correct':sum(s['raw_semantics_correct'] for s in scores),'compiled_semantics_correct':sum(s['compiled_semantics_correct'] for s in scores),'covered':sum(s['covered'] for s in scores),
        'unknown_clause_errors':sum(not s['compiled_semantics_correct'] for s in scores if not s['expected_supported']),
        'lineage_problems':sum(len(c.get('source_validation',{}).get('quote_and_parameter_problems',[])) for c in report['cases']),
        'all_drafts_unapproved':all(c.get('draft_only') for c in report['cases']),'failed_cases':sum(c['status']=='FAILED' for c in report['cases'])}
    metrics['compiled_complete_rule_mapping']=metrics['compiled_semantics_correct']/total;metrics['raw_complete_rule_mapping']=metrics['raw_semantics_correct']/total;metrics['clause_coverage']=metrics['covered']/total
    report['metrics']=metrics;report['status']='DEVELOPER_HOLDOUT_CHECKS_PASS_REVIEW_PENDING' if metrics['compiled_complete_rule_mapping']>=.90 and metrics['clause_coverage']==1 and metrics['unknown_clause_errors']==0 and metrics['lineage_problems']==0 and metrics['all_drafts_unapproved'] and metrics['failed_cases']==0 else 'NOT_ACCEPTED'
    save();print(json.dumps({'status':report['status'],'metrics':metrics},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
