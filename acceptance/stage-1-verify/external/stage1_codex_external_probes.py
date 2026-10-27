import sys,json,shutil,csv
from pathlib import Path
root=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parent/'repo';sys.path.insert(0,str(root));sys.path.insert(0,str(root/'tools'))
import yaml
from geoacceptance.compare import compare_batches
out=[]
base=Path(__file__).resolve().parent/'cases';base.mkdir(exist_ok=True)
def clone(name,src='clean'):
 p=base/name;shutil.copytree(root/'examples'/src,p,dirs_exist_ok=True);return p
def save(case,b,a):
 v=compare_batches(b,a);out.append({'case':case,'result':v});print(case, 'before',v['before']['aggregate'],'after',v['after']['aggregate'],'compare',v['overall'],'counts',v['counts'])
save('blocked_unchanged',root/'examples'/'blocked',root/'examples'/'blocked')
save('after_missing_evidence',root/'examples'/'clean',root/'examples'/'ambiguous')
# one stale row, then remove that entity instead of repairing it
b=clone('stale_before');a=clone('deleted_after')
with (b/'poi.csv').open(encoding='utf-8',newline='') as f: rows=list(csv.reader(f))
rows[1][-1]='2026-08-01T00:00:00Z'
with (b/'poi.csv').open('w',encoding='utf-8',newline='') as f:csv.writer(f).writerows(rows)
with (a/'poi.csv').open('w',encoding='utf-8',newline='') as f:csv.writer(f).writerows([rows[0]]+rows[2:])
save('failing_entity_deleted',b,a)
# disable R09; no finding must not mean fixed
b=clone('stale_before2');shutil.copyfile(base/'stale_before'/'poi.csv',b/'poi.csv');a=clone('stale_unapproved');shutil.copyfile(b/'poi.csv',a/'poi.csv')
r=yaml.safe_load((a/'approved-rules.yaml').read_text(encoding='utf-8'));next(x for x in r['rules'] if x['rule_id']=='R09')['status']='DRAFT';(a/'approved-rules.yaml').write_text(yaml.safe_dump(r,allow_unicode=True,sort_keys=False),encoding='utf-8')
save('after_rule_unapproved',b,a)
# two failures on the same unique entity are not duplicate identities
b=clone('unique_two_failures');a=clone('unique_repaired')
with (b/'poi.csv').open(encoding='utf-8',newline='') as f: rows=list(csv.reader(f))
rows[1][2]='invalid_category';rows[1][-1]='2026-08-01T00:00:00Z'
with (b/'poi.csv').open('w',encoding='utf-8',newline='') as f:csv.writer(f).writerows(rows)
save('unique_entity_multiple_findings',b,a)
Path(__file__).with_name('external-stage1-results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')

