import sys,json,csv,shutil
from pathlib import Path
root=Path(sys.argv[1]).resolve() if len(sys.argv)>1 else Path(__file__).resolve().parent/'repo';sys.path.insert(0,str(root));sys.path.insert(0,str(root/'tools'))
import yaml
from geoacceptance.validate import validate_bundle
from geoacceptance.compare import compare_batches
base=Path(__file__).resolve().parent/'additional';base.mkdir(exist_ok=True)
def clone(n):
 p=base/n;shutil.copytree(root/'examples'/'clean',p,dirs_exist_ok=True);return p
out=[]
b=clone('clean_before');a=clone('clean_entity_removed')
with (a/'poi.csv').open(encoding='utf-8',newline='') as f: rows=list(csv.reader(f))
with (a/'poi.csv').open('w',encoding='utf-8',newline='') as f:csv.writer(f).writerows([rows[0]]+rows[2:])
r=compare_batches(b,a);print('delete_clean_entity',r['overall'],r['scope']['entities_removed_after']);out.append({'case':'delete_clean_entity','result':r})
p=clone('missing_name_empty_field_rule')
rules=yaml.safe_load((p/'approved-rules.yaml').read_text(encoding='utf-8'));next(x for x in rules['rules'] if x['rule_id']=='R01')['parameters']['fields']=[]
(p/'approved-rules.yaml').write_text(yaml.safe_dump(rules,allow_unicode=True,sort_keys=False),encoding='utf-8')
with (p/'poi.csv').open(encoding='utf-8',newline='') as f:rows=list(csv.reader(f))
idx=rows[0].index('name');rows=[[v for i,v in enumerate(row) if i!=idx] for row in rows]
with (p/'poi.csv').open('w',encoding='utf-8',newline='') as f:csv.writer(f).writerows(rows)
r=validate_bundle(p);print('empty_required_field_config',r['aggregate_verdict'],'rejections',r['config_rejections']);out.append({'case':'empty_required_field_config','result':r})
Path(__file__).with_name('additional-results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')

