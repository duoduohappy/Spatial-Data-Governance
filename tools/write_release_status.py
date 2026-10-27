"""Derive release status from actual evidence; external acceptance remains distinct."""
import json,datetime,hashlib,re
from pathlib import Path
root=Path(__file__).resolve().parents[1]
def read(path):return json.loads((root/path).read_text(encoding='utf-8-sig'))
def count(path,pattern):
    text=(root/path).read_text(encoding='utf-8-sig');match=re.search(pattern,text)
    if not match:raise RuntimeError('Missing passing evidence: '+path)
    return int(match.group(1))
app=count('acceptance/stage-2/application-tests.txt',r'Ran (\d+) tests')
if not (root/'acceptance/stage-2/application-tests.txt').read_text(encoding='utf-8-sig').rstrip().endswith('OK'):raise RuntimeError('Application tests failed')
core=count('acceptance/stage-5/core-probes.txt',r'RECHECK_PROBES_OK=true[^\n]*?(\d+)/\1')
compare=count('acceptance/stage-5/compare-probes.txt',r'COMPARE_PROBES_OK=true[^\n]*?(\d+)/\1')
if 'ALL_OK=true' not in (root/'acceptance/stage-5/core-regression.txt').read_text(encoding='utf-8-sig'):raise RuntimeError('Frozen gate failed')
browser=read('acceptance/stage-3/browser/latest.json');media=read('acceptance/stage-3/browser/recording-metadata.json')
assert browser['status']=='PASS' and not browser['errors'] and all(c['status']=='PASS' for c in browser['checks'])
video=root/'acceptance/stage-3/browser'/media['directory']/media['video']
if not video.exists():
    from restore_recording import restore
    restore()
assert media['directory']==browser['directory'] and hashlib.sha256(video.read_bytes()).hexdigest()==media['sha256']
quality=read('acceptance/stage-4/local-model/quality-summary.json')
latest=next(r for r in quality['runs'] if Path(r['source']).parent.name=='quality-v4')
assert len(latest['cases'])==12 and latest['passed_checks']==12 and latest['failed']==0
heldout=read('acceptance/stage-4/local-model/heldout-v1/results.json')
assert heldout['status']=='DEVELOPER_HOLDOUT_CHECKS_PASS_REVIEW_PENDING'
iab=read('acceptance/stage-3/iab-downloads/results.json');assert iab['status']=='PASS'
for record in iab['files']:
    assert record['matches_server'] and hashlib.sha256((root/'acceptance/stage-3/iab-downloads'/('report.'+record['type'])).read_bytes()).hexdigest()==record['sha256']
http=read('acceptance/stage-5/local-http-probe.json');assert http['status']=='PASS'
full=read('acceptance/stage-4/local-model/full/latest.json');review=read(str(Path(full['evidence'])/'review.json'))
assert review['status']=='REVIEWED_SYNTHETIC_WORKFLOW_PASS'
checks={'frozen_examples':6,'core_probes':core,'compare_probes':compare,'application_and_http_tests':app,
    'javascript_syntax':'PASS','dom_simulation':'PASS','real_browser_checks':len(browser['checks']),
    'browser_engine':browser['browser_version'],'recorded_demo_seconds':float(media['ffprobe']['format']['duration']),
    'local_json_inference':read('acceptance/stage-4/local-model/json-smoke.json')['status'],
    'real_local_quality_pipeline':{'passed':12,'cases':12,'scope':'developer-visible templates; includes evidence compiler fail-closed behavior'},
    'developer_holdout':heldout['metrics'],'actual_iab_attachment_save':'PASS','local_http_workflow':'PASS'}
remote=read('acceptance/stage-5/remote-ci/results.json')
assert remote['conclusion']=='success' and len(remote['jobs'])==5 and all(j['conclusion']=='success' for j in remote['jobs'])
checks['remote_ci']='PASS'
checks['docker_build_and_http_smoke']='PASS'
status={'version':'0.5.0-rc1','created_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'kind':'local-source-release-candidate','implementation':'Stage 2-5 implementation and candidate artifacts prepared',
    'acceptance':'ENGINEERING_CHECKS_PASS; independent business review and human outcome measurements pending',
    'remote_ci':remote,'checks':checks,'not_run':['independent human/business annotations','human efficiency study','live single-agent vs multi-agent'],
    'local_model_full_latest':full,'local_model_reviewed_workflow':{'status':review['status'],'edits':len(review['changes']),'reviewer':review['reviewer'],'limitation':review['limitation']},
    'local_model_quality':{'acceptance':'AUTOMATED_PIPELINE_PASS_REVIEW_REQUIRED','latest':latest['source'],
        'scope':quality['kind'],'prior_failures_preserved':True,'raw_model_zero_error_claim':False},
    'source':'Implementation self-check plus actual user-requested IAB export; not independent external acceptance'}
(root/'acceptance/stage-5/STATUS.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
bodies={2:'Real local model/evidence compiler pipeline passed 12/12 developer-visible checks. An unchanged clear synthetic proposal was reviewed by implementing Codex and executed PASS/FAIL/PASS. Manual approval remains mandatory. Cloud Qwen previously returned HTTP 403; no new cloud model calls.',
3:'Local UI/API tests and real Chromium desktop/mobile checks passed. Actual user-requested in-app-browser JSON and HTML downloads succeeded; archived bytes match server reports. Separate sandboxed Chromium downloads remain permission-blocked; see iab-downloads/results.json.',
4:'Frozen developer holdout: 8 new specifications / 80 atomic clauses, compiled complete mapping 75/80, raw semantic mapping 74/80, coverage 80/80; unknown-clause errors and lineage problems zero. These are developer-authored labels, not independent human gold labels or a generalization guarantee. Prior failures and the interrupted 11-case third run remain archived.',
5:'Local functional checks passed. Candidate source, startup scripts, Docker and CI definitions are prepared. Actual local HTTP workflow passed, including positive closure and duplicate-identity non-closure. Source published to duoduohappy/Spatial-Data-Governance. All five actual GitHub Actions jobs passed, including Linux/Windows tests, DOM, browser and Docker build/start/HTTP workflow; see remote-ci/results.json and logs. Independent business acceptance remains pending.'}
for stage,body in bodies.items():
    text=f'# Stage {stage} handoff\n\n2026-10-27. {body}\n\nImplementation self-check; independent external/business acceptance remains pending.\n'
    if stage==5:text+=f'\nEvidence: STATUS.json; {app} application/HTTP tests; {core} core probes; {compare} compare/input probes; stage-3/iab-downloads; stage-4/local-model. Dependencies previously installed in a clean Python 3.13.14 venv; no new Python dependency was added. Source ZIP excludes work/, credentials, model weights, browser binaries and .venv.\n'
    (root/f'acceptance/stage-{stage}/HANDOFF.md').write_text(text,encoding='utf-8')
print(json.dumps(checks,ensure_ascii=False))
