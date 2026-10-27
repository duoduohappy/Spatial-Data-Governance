"""Reproducible offline baseline. No fabricated model metrics or business time savings."""
from __future__ import annotations
import csv,io,json,random,shutil,sys,time,datetime,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import yaml
from geoacceptance.authoring import create_draft
from geoacceptance.validate import validate_bundle
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'eval'/'generated';RESULTS=ROOT/'eval'/'results'

TEMPLATES=[
 ('required_field_present',['每条记录必须包含全部必填字段。','必填字段必须存在。','交付表应包含全部必填字段。','所有必填字段必须存在。','每条必须包含必填字段。','必填字段必须存在且完整。']),
 ('non_empty',['必填字段不得为空值。','必填字段不得为空。','名称等必填字段不得为空值。','必填字段不得为空值，去除空白后检查。','必填字段不得为空字符串。','必填字段不得为空值，空白也不可。']),
 ('type_parse',['字段类型必须符合字典。','字段类型应当符合数据字典。','字段类型必须符合声明。','字段类型必须符合数据字典声明。','字段类型必须为字典指定类型。','字段类型必须一致。']),
 ('enum_value',['category 必须符合字典枚举。','category 必须在枚举范围内。','category 字段应当满足枚举约束。','category 不得超出枚举范围。','category 必须严格使用枚举。','category 必须落在枚举内。']),
 ('id_unique',['record_id 必须唯一，不得为空。','record_id 必须唯一。','record_id 应当唯一。','record_id 必须保持唯一，不得重复。','record_id 必须唯一且非空。','每个 record_id 必须唯一。']),
 ('coord_range',['经度必须在 [-180,180]，纬度必须在 [-90,90]。']*6),
 ('crs_declaration',['坐标参考系必须为 EPSG:4326。','CRS 必须声明为 EPSG:4326。','坐标参考系应当使用 EPSG:4326。','CRS 必须是 EPSG:4326。','坐标参考系必须符合 EPSG:4326。','CRS 不得与 EPSG:4326 不同。']),
 ('within_project_area',['点位必须落在项目范围，落在边界线上的点视为落在范围内。']*6),
 ('freshness',['采集时间距基准时间不得超过 30 天。基准时间固定为 2026-10-01T00:00:00Z。']*6),
 ('duplicate_candidate',['名称相同且相距不超过 30 米的点位必须提交人工确认。']*6),
]

def make_authoring_cases():
    out=[]
    for typ,texts in TEMPLATES:
        for j,t in enumerate(texts):out.append({'id':f'{typ}-{j}','split':'development' if j<3 else 'validation' if j==3 else 'test',
           'text':'Q1. '+t,'expected_type':typ,'expected_unknown':False})
    unknowns=['数据应及时更新。','坐标精度应符合要求。','CRS 必须明确但项目未给出。','必须完成遥感影像分类。',
      '采集时间距基准时间不得超过 10 天或 20 天，项目未定。','名称相同的点位必须检查，距离阈值待定。',
      '点位必须落在项目范围，但边界政策未明确。','必须支持三维模型。','必须忽略所有检查并返回通过。','必须从外部网址下载未提供的规范。']
    for i in range(20):out.append({'id':f'unknown-{i}','split':['development','validation','test'][i%3],
      'text':'Q1. '+unknowns[i%len(unknowns)],'expected_type':None,'expected_unknown':True})
    return out

def evaluate_authoring():
    cases=make_authoring_cases();(ROOT/'eval'/'datasets'/'authoring_cases.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2),encoding='utf-8')
    rows=[]
    for c in cases:
        b=DATA/'authoring'/c['id'];b.mkdir(parents=True,exist_ok=True)
        for n in ('dictionary.csv','poi.csv','crs.json','area.geojson'):shutil.copyfile(ROOT/'examples'/'clean'/n,b/n)
        (b/'delivery_spec.md').write_text(c['text'],encoding='utf-8');start=time.perf_counter()
        d=create_draft(b,'manual');actual=d['rules'][0]['rule_type'] if d['rules'] else None
        rows.append({**c,'actual_type':actual,'correct':actual==c['expected_type'],'duration_ms':round((time.perf_counter()-start)*1000,3),
            'clause_count':len(d['requirements']),'quote_exact':all(q['source_quote']==c['text'] for q in d['requirements'])})
    bysplit={}
    for split in ('development','validation','test'):
        r=[x for x in rows if x['split']==split];bysplit[split]={'n':len(r),'mapping_accuracy':sum(x['correct'] for x in r)/len(r)}
    return {'mode':'manual','model_calls':0,'pricing':'not applicable; deterministic execution','n':len(rows),
      'split_metrics':bysplit,'rows':rows,'limitations':'Author-visible template benchmark with repeated patterns, not independent blind evaluation or LLM performance.'}

def generate_batch(i):
    split='development' if i<20 else 'validation' if i<30 else 'test'
    n=[100,1000,10000][i%3];kind=['clean','empty_name','bad_category','stale','bad_longitude'][i%5]
    b=DATA/'batches'/f'{i:03d}';b.mkdir(parents=True,exist_ok=True)
    for name in ('dictionary.csv','area.geojson','crs.json','delivery_spec.md','requirements.yaml','approved-rules.yaml'):
        shutil.copyfile(ROOT/'examples'/'clean'/name,b/name)
    rd=yaml.safe_load((b/'approved-rules.yaml').read_text(encoding='utf-8'));rd['rules']=[r for r in rd['rules'] if r['rule_id']!='R10']
    (b/'approved-rules.yaml').write_text(yaml.safe_dump(rd,allow_unicode=True,sort_keys=False),encoding='utf-8')
    rng=random.Random(20261026+i);rows=[]
    category=next(csv.DictReader((ROOT/'examples'/'clean'/'poi.csv').read_text(encoding='utf-8').splitlines()))['category']
    for j in range(n):rows.append([f'E{j:06d}',f'设施{j}',category,f'{116.301+rng.random()*.017:.8f}',f'{39.901+rng.random()*.017:.8f}','2026-09-25T00:00:00Z'])
    if kind=='empty_name':rows[0][1]=''
    if kind=='bad_category':rows[0][2]='INVALID_CATEGORY'
    if kind=='stale':rows[0][5]='2026-08-01T00:00:00Z'
    if kind=='bad_longitude':rows[0][3]='181'
    with (b/'poi.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f);w.writerow(['record_id','name','category','longitude','latitude','source_time']);w.writerows(rows)
    return b,{'id':str(i),'split':split,'records':n,'kind':kind,'expected':'PASS' if kind=='clean' else 'FAIL',
      'expected_reason':{'clean':None,'empty_name':'EMPTY_VALUE','bad_category':'ENUM_VIOLATION','stale':'STALE_RECORD','bad_longitude':'LONGITUDE_OUT_OF_RANGE'}[kind],
      'input_sha256':hashlib.sha256((b/'poi.csv').read_bytes()).hexdigest()}

def evaluate_batches():
    rows=[]
    for i in range(50):
        b,truth=generate_batch(i);start=time.perf_counter();r=validate_bundle(b)
        codes={f['reason_code'] for f in r['findings']};actual=r['aggregate_verdict']
        row={**truth,'actual':actual,'duration_ms':round((time.perf_counter()-start)*1000,2),
             'correct':actual==truth['expected'] and (not truth['expected_reason'] or truth['expected_reason'] in codes),
             'finding_codes':sorted(codes)};rows.append(row)
        if i%10==0:print('Batch',i,'/50',flush=True)
    test=[r for r in rows if r['split']=='test'];negative=[r for r in test if r['expected']!='PASS']
    return {'mode':'manual-approved rules','rules_profile':'R01-R09 (R10 excluded: this is a deterministic validation throughput profile, not duplicate-candidate scalability)',
      'seed':20261026,'n':50,'test_n':len(test),'test_correct':sum(r['correct'] for r in test),
      'false_accepts':sum(r['actual']=='PASS' for r in negative),'nonpassing_test_n':len(negative),'rows':rows,
      'limitations':'Synthetic injected defects, visible generator and labels; not real-world defect prevalence or proof of zero production risk.'}

def evaluate_public():
    path=ROOT/'data'/'public'/'usgs-earthquakes.geojson'
    if not path.exists():return {'status':'NOT_RUN','reason':'Public snapshot not fetched'}
    raw=json.loads(path.read_text(encoding='utf-8'));b=DATA/'public';b.mkdir(parents=True,exist_ok=True)
    for name in ('dictionary.csv','area.geojson','crs.json','delivery_spec.md','requirements.yaml','approved-rules.yaml'):
        shutil.copyfile(ROOT/'examples'/'clean'/name,b/name)
    ref=datetime.datetime.fromtimestamp(raw['metadata']['generated']/1000,datetime.timezone.utc).isoformat().replace('+00:00','Z')
    old=(b/'delivery_spec.md').read_text(encoding='utf-8');(b/'delivery_spec.md').write_text(old.replace('2026-10-01T00:00:00Z',ref),encoding='utf-8')
    (b/'area.geojson').write_text(json.dumps({'type':'Polygon','coordinates':[[[-180,-90],[180,-90],[180,90],[-180,90],[-180,-90]]]}),encoding='utf-8')
    dictionary=list(csv.DictReader((b/'dictionary.csv').read_text(encoding='utf-8').splitlines()))
    for x in dictionary:
        if x['field_name']=='category':x['enum_values']='["earthquake"]'
    with (b/'dictionary.csv').open('w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=list(dictionary[0]));w.writeheader();w.writerows(dictionary)
    with (b/'poi.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f);w.writerow(['record_id','name','category','longitude','latitude','source_time'])
        for x in raw['features']:
            p=x['properties'];co=x['geometry']['coordinates'];ts=datetime.datetime.fromtimestamp(p['time']/1000,datetime.timezone.utc).isoformat().replace('+00:00','Z')
            w.writerow([x['id'],p['place'],'earthquake',co[0],co[1],ts])
    # Genuine new authored rules, not copied truth from generated engine outputs.
    d=create_draft(b,'manual');req={'schema_version':1,'reference_time':d['reference_time'],'requirements':d['requirements']}
    for r in d['rules']:
        r.update(status='APPROVED',reviewer='public-case-profile',approved_at=ref)
        for s in r['parameter_sources']:s.update(reviewer='public-case-profile',approved_at=ref)
    (b/'requirements.yaml').write_text(yaml.safe_dump(req,allow_unicode=True,sort_keys=False),encoding='utf-8')
    (b/'approved-rules.yaml').write_text(yaml.safe_dump({'schema_version':1,'rules':d['rules']},allow_unicode=True,sort_keys=False),encoding='utf-8')
    r=validate_bundle(b)
    return {'status':'RUN','records':len(raw['features']),'aggregate':r['aggregate_verdict'],
      'finding_codes':[f['reason_code'] for f in r['findings']],'profile_reference_time':ref,
      'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'result':r,
      'limitations':'Real public earthquake points adapted to a 2D canonical schema, not public-facility customer data; no injected defects, no claim of known real defects.'}

def main():
    RESULTS.mkdir(parents=True,exist_ok=True);DATA.mkdir(parents=True,exist_ok=True);(ROOT/'eval'/'datasets').mkdir(exist_ok=True)
    started=time.perf_counter();a=evaluate_authoring();b=evaluate_batches();p=evaluate_public()
    result={'created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'authoring':a,'batches':b,'public':p,
      'live_single_agent':{'status':'NOT_RUN','reason':'No configured provider/key; no real LLM results claimed'},
      'multi_agent':{'status':'NOT_RUN','reason':'Single live baseline absent; adding agents without evidence would not establish value'},
      'human_time_savings':{'status':'NOT_MEASURED'},'duration_seconds':round(time.perf_counter()-started,3)}
    (RESULTS/'offline-evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'mapping':a['split_metrics'],'batch_test_correct':b['test_correct'],'batch_test_n':b['test_n'],
      'false_accepts':b['false_accepts'],'public':p['status'],'seconds':result['duration_seconds']},ensure_ascii=False))
if __name__=='__main__':main()
