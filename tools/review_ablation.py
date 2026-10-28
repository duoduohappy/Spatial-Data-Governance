"""Three-arm local-only evaluation against a frozen developer-labelled dataset."""
from __future__ import annotations
import argparse,datetime,hashlib,json,os,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from geoacceptance.authoring import create_draft
from geoacceptance.collaboration import create_collaborative_draft
from geoacceptance.llm import CompatibleClient,ModelConfig
from tools.heldout_acceptance import score
from tools.live_acceptance import source_validation

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--dataset',required=True);parser.add_argument('--out',required=True);args=parser.parse_args()
    dataset=Path(args.dataset).resolve();out=Path(args.out).resolve();out.mkdir(parents=True,exist_ok=True)
    manifest_file=dataset/'manifest.json';manifest=json.loads(manifest_file.read_text(encoding='utf-8'));digest=hashlib.sha256(manifest_file.read_bytes()).hexdigest()
    for c in manifest['cases']:assert hashlib.sha256((dataset/c['id']/'delivery_spec.md').read_bytes()).hexdigest()==c['document_sha256']
    for k in list(os.environ):
        if k.startswith('GA_') or k in ('DASHSCOPE_API_KEY','DEEPSEEK_API_KEY','OPENAI_API_KEY','OLLAMA_API_KEY'):os.environ.pop(k,None)
    os.environ.update(GA_PROVIDER='ollama',GA_MAX_CALLS='1',GA_TIMEOUT_SECONDS='300')
    provenance={str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.rglob('*.py') if 'work' not in p.relative_to(ROOT).parts}
    path=out/'results.json';report=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'status':'RUNNING','dataset_exposure':'Second and subsequent runs are exposed developer regression; never relabel as independent holdout','created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'manifest_sha256':digest,'scope':manifest['scope'],'provenance':provenance,'criteria':manifest['adoption_criteria'],'cases':[]}
    assert report['manifest_sha256']==digest and report['provenance']==provenance,'Cannot resume with changed source or data'
    done={(r['case'],r['strategy']) for r in report['cases']}
    def save():path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    for number,case in enumerate(manifest['cases']):
        order=manifest['arms'][number%3:]+manifest['arms'][:number%3]
        for strategy in order:
            if (case['id'],strategy) in done:continue
            client=CompatibleClient(ModelConfig.from_env());start=time.perf_counter();row={'case':case['id'],'strategy':strategy,'status':'RUNNING','human_review':'NOT_RUN'}
            try:
                bundle=dataset/case['id'];draft=create_draft(bundle,'live',client) if strategy=='single' else create_collaborative_draft(bundle,client,strategy)
                row.update(status='COMPLETED',draft=draft,scores=score(case,draft),lineage=source_validation(bundle,draft),all_unapproved=all(r['status']=='DRAFT' and not r['reviewer'] for r in draft['rules']))
            except Exception as e:row.update(status='FAILED',error_type=type(e).__name__,error=str(e)[:1600])
            row.update(collaboration_outputs=getattr(client,'collaboration_outputs',[]),calls=client.calls,duration_ms=round((time.perf_counter()-start)*1000,2));report['cases'].append(row);save()
            print(json.dumps({'case':case['id'],'strategy':strategy,'status':row['status'],'correct':sum(s['compiled_semantics_correct'] for s in row.get('scores',[])),'calls':len(client.calls),'duration_ms':row['duration_ms'],'error':row.get('error')},ensure_ascii=False),flush=True)
    total=sum(len(c['truth']) for c in manifest['cases']);metrics={}
    for strategy in manifest['arms']:
        rows=[r for r in report['cases'] if r['strategy']==strategy];scores=[s for r in rows for s in r.get('scores',[])]
        usages=[c.get('usage',{}).get('total_tokens') if c.get('usage') else None for r in rows for c in r['calls']]
        metrics[strategy]={'correct':sum(s['compiled_semantics_correct'] for s in scores),'clauses':total,'covered':sum(s['covered'] for s in scores),'unknown_errors':sum(not s['compiled_semantics_correct'] for s in scores if not s['expected_supported']),'failed_cases':sum(r['status']!='COMPLETED' for r in rows),'model_calls':sum(len(r['calls']) for r in rows),'tokens':sum(usages) if all(u is not None for u in usages) else None,'duration_ms':round(sum(r['duration_ms'] for r in rows),2),'all_unapproved':all(r.get('all_unapproved',False) for r in rows),'lineage_problems':sum(len(r.get('lineage',{}).get('quote_and_parameter_problems',[])) for r in rows)}
    baseline=metrics['single'];dual=metrics['dual_review'];criteria=manifest['adoption_criteria']
    passed=not dual['failed_cases'] and not dual['unknown_errors'] and dual['all_unapproved'] and not dual['lineage_problems'] and dual['covered']==total and dual['correct']>=baseline['correct']+criteria['minimum_correct_improvement_over_single'] and baseline['tokens'] and dual['tokens'] and dual['tokens']<=baseline['tokens']*criteria['max_token_ratio']
    report.update(status='MEASURED_DEVELOPER_REGRESSION_NOT_INDEPENDENT_VALIDATION',metrics=metrics,default_strategy='single',adoption='DEVELOPER_THRESHOLD_MET_REQUIRES_EXTERNAL_VALIDATION' if passed else 'DO_NOT_PROMOTE_DUAL_REVIEW_DEFAULT',note='Actual local calls. Same local model; role separation is not statistical independence. Modification counts are proxies, not measured human effort.');save();print(json.dumps({'adoption':report['adoption'],'metrics':metrics},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
