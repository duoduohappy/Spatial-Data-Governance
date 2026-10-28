"""Core regression of new authoring/service/HTTP surfaces. No provider calls."""
import copy,csv,hashlib,io,json,os,sys,tempfile,threading,time,unittest,urllib.request,urllib.error
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from geoacceptance.service import Service,Conflict,normalize_geojson,INPUTS
from geoacceptance.authoring import create_draft,normalize_proposal,outbound_preview,manual_proposal
from geoacceptance.llm import ModelConfig,CompatibleClient,ModelError
from geoacceptance.server import AppServer
ROOT=Path(__file__).resolve().parents[1]

def wait(s,j):
    for _ in range(1000):
        r=s.job(j['id'])
        if r['status'] not in ('QUEUED','RUNNING'):return r
        time.sleep(.01)
    raise AssertionError('Task timeout')

class AppTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'work');self.s=Service(Path(self.tmp.name)/'app')
    def tearDown(self):self.s.close();self.tmp.cleanup()
    def draft(self,name='clean'):
        p=self.s.example(name);j=wait(self.s,self.s.submit(p['id'],'draft',p['revision'],'draft'))
        self.assertEqual(j['status'],'COMPLETED',j['error']);return self.s.detail(p['id'])
    def approved(self,name='clean'):
        p=self.draft(name);return self.s.approve(p['id'],p['revision'],p['draft'],'test-reviewer')
    def test_all_sample_drafts_default_unapproved(self):
        for name in ['clean','defective','ambiguous']:
            p=self.draft(name);self.assertTrue(p['draft']['requirements']);self.assertTrue(all(r['status']=='DRAFT' for r in p['draft']['rules']))
            with self.assertRaises(Conflict):self.s.submit(p['id'],'validate',p['revision'],'unapproved')
    def test_clean_defective_and_unknown(self):
        for name,want in [('clean','PASS'),('defective','FAIL'),('ambiguous','INDETERMINATE')]:
            p=self.approved(name);j=wait(self.s,self.s.submit(p['id'],'validate',p['revision'],'run'))
            self.assertEqual(j['status'],'COMPLETED',j['error']);self.assertEqual(j['result']['aggregate_verdict'],want)
    def test_stale_review(self):
        p=self.draft();self.s.approve(p['id'],p['revision'],p['draft'],'A')
        with self.assertRaises(Conflict):self.s.approve(p['id'],p['revision'],p['draft'],'B')
    def test_tampered_quote_and_threshold(self):
        p=self.draft();d=copy.deepcopy(p['draft']);d['requirements'][0]['source_quote']='伪造'
        with self.assertRaises(ValueError):self.s.approve(p['id'],p['revision'],d,'A')
        d=copy.deepcopy(p['draft']);next(r for r in d['rules'] if r['rule_id']=='R09')['parameters']['max_age_days']=365
        with self.assertRaises(ValueError):self.s.approve(p['id'],p['revision'],d,'A')
    def test_missing_clause_and_downgrade_cannot_disappear(self):
        p=self.draft();d=copy.deepcopy(p['draft']);d['requirements']=d['requirements'][1:]
        with self.assertRaises(ValueError):self.s.approve(p['id'],p['revision'],d,'A')
        d=copy.deepcopy(p['draft']);d['requirements'][0]['required_for_release']=False
        normalized=normalize_proposal(d,self.s.path(p['id']));self.assertTrue(normalized['requirements'][0]['required_for_release'])
    def test_review_can_correct_model_misclassified_advisory(self):
        p=self.draft();draft=copy.deepcopy(p['draft'])
        clause=next(q for q in draft['requirements'] if q['requirement_id']=='C2')
        clause['required_for_release']=True
        with self.s.connect() as c:c.execute('UPDATE projects SET draft=? WHERE id=?',(json.dumps(draft),p['id']))
        clause['required_for_release']=False
        reviewed=self.s.approve(p['id'],p['revision'],draft,'test-reviewer')
        corrected=next(q for q in reviewed['approval']['requirements_doc']['requirements'] if q['requirement_id']=='C2')
        self.assertFalse(corrected['required_for_release'])

    def test_no_external_records_in_preview(self):
        preview=outbound_preview(ROOT/'examples'/'defective');serialized=json.dumps(preview)
        self.assertNotIn('SD-0001',serialized);self.assertNotIn('116.3',serialized)
    def test_idempotency_and_input_immutability(self):
        p=self.draft();p=self.s.approve(p['id'],p['revision'],p['draft'],'A')
        original={n:(self.s.path(p['id'])/n).read_bytes() for n in INPUTS}
        j=self.s.submit(p['id'],'validate',p['revision'],'same');j2=self.s.submit(p['id'],'validate',p['revision'],'same');self.assertEqual(j['id'],j2['id']);wait(self.s,j)
        self.assertEqual(original,{n:(self.s.path(p['id'])/n).read_bytes() for n in INPUTS})
    def test_snapshot_changed_after_approval(self):
        p=self.approved();(self.s.path(p['id'])/'poi.csv').write_text('tamper',encoding='utf-8')
        j=wait(self.s,self.s.submit(p['id'],'validate',p['revision'],'run'));self.assertEqual(j['status'],'FAILED')
    def test_correction_and_compare(self):
        p=self.approved('defective');jb=wait(self.s,self.s.submit(p['id'],'validate',p['revision'],'b'))
        q=self.s.corrected(p['id'],p['revision'],{'poi.csv':(ROOT/'examples'/'corrected'/'poi.csv').read_text(encoding='utf-8')},'corrected')
        ja=wait(self.s,self.s.submit(q['id'],'validate',q['revision'],'a'));r=self.s.compare(jb['id'],ja['id'])
        self.assertNotEqual(r['overall'],'LEDGER_CLOSED_ACCEPTED') # duplicated original identity stays unknown
        self.assertGreater(r['counts'].get('closed',0),0)
    def test_geojson_no_silent_skipping(self):
        good={'type':'FeatureCollection','features':[{'type':'Feature','properties':{'record_id':'x','name':'X'},'geometry':{'type':'Point','coordinates':[116,39]}}]}
        self.assertIn('116,39',normalize_geojson(json.dumps(good)))
        good['features'][0]['geometry']['type']='Polygon'
        with self.assertRaises(ValueError):normalize_geojson(json.dumps(good))
    def test_provider_retry_budget_and_usage_unknown(self):
        c=ModelConfig('http://localhost:11434/v1','local','',max_calls=2,input_usd_per_million=0,output_usd_per_million=0)
        attempts=[]
        def transport(p):
            attempts.append(p)
            if len(attempts)==1:return {'choices':[{'message':{'content':'bad'}}]}
            return {'choices':[{'message':{'content':'{"requirements":[],"rules":[]}'}}]}
        client=CompatibleClient(c,transport);client.complete([{'role':'user','content':'x'}]);self.assertEqual(len(client.calls),2);self.assertIsNone(client.calls[-1]['usage']);self.assertIsNone(client.calls[-1]['cost_usd'])
        c.budget_usd=0;c.input_usd_per_million=100
        with self.assertRaises(ModelError):CompatibleClient(c,transport).complete([{'role':'user','content':'x'}])
    def test_nonfinite_prices_and_invalid_usage(self):
        from dataclasses import replace
        cfg=ModelConfig('http://localhost:11434/v1','local','',input_usd_per_million=0,output_usd_per_million=0)
        for field in ('input_usd_per_million','output_usd_per_million','budget_usd'):
            for value in (float('nan'),float('inf'),-1,True):
                with self.assertRaises(ModelError):
                    CompatibleClient(replace(cfg,**{field:value}),lambda _:self.fail('Must not call provider')).complete([{'role':'user','content':'x'}])
        client=CompatibleClient(cfg,lambda _:{'choices':[{'message':{'content':'{}'}}],
            'usage':{'prompt_tokens':-10,'completion_tokens':True,'total_tokens':float('nan')}})
        client.complete([{'role':'user','content':'x'}])
        self.assertIsNone(client.calls[0]['cost_usd'])
        self.assertEqual(client.calls[0]['usage'],{'prompt_tokens':None,'completion_tokens':None,'total_tokens':None})

    def test_deepseek_profile_and_currency_contract(self):
        from unittest.mock import patch
        from dataclasses import replace
        with patch.dict(os.environ,{'GA_PROVIDER':'deepseek','DEEPSEEK_API_KEY':'unit-test-placeholder','GA_BASE_URL':'','GA_MODEL':'','GA_CURRENCY':''},clear=True):
            cfg=ModelConfig.from_env()
        self.assertEqual(cfg.base_url,'https://api.deepseek.com')
        self.assertEqual(cfg.model,'deepseek-flash')
        self.assertEqual(cfg.monetary(),(2.0,8.0,0.5))
        self.assertNotIn(cfg.api_key,json.dumps(cfg.public()))
        payloads=[]
        def transport(payload):
            payloads.append(payload)
            return {'choices':[{'message':{'content':'{}'},'finish_reason':'stop'}],
                    'usage':{'prompt_tokens':100,'completion_tokens':200,'total_tokens':300}}
        client=CompatibleClient(cfg,transport);client.complete([{'role':'user','content':'JSON'}])
        self.assertEqual(payloads[0]['thinking'],{'type':'disabled'})
        self.assertEqual(client.calls[0]['currency'],'CNY')
        self.assertAlmostEqual(client.calls[0]['cost'],.0018)
        self.assertIsNone(client.calls[0]['cost_usd'])
        for bad in (replace(cfg,base_url='https://example.com'),replace(cfg,api_key=''),replace(cfg,input_usd_per_million=1)):
            with self.assertRaises(ModelError):CompatibleClient(bad,lambda _:self.fail('Must not call provider')).complete([{'role':'user','content':'JSON'}])
        self.assertFalse(replace(cfg,api_key='').public()['configured'])
        from contextlib import redirect_stdout
        from geoacceptance.deepseek_launcher import main as launch
        stream=io.StringIO()
        with patch.dict(os.environ,{},clear=True),redirect_stdout(stream),patch('geoacceptance.deepseek_launcher.read_key_file',return_value=None):
            self.assertEqual(launch(['--check']),2)
        self.assertFalse(json.loads(stream.getvalue())['key_present'])


    def test_qwen_beijing_profile_and_launcher(self):
        from unittest.mock import patch
        from dataclasses import replace
        from contextlib import redirect_stdout
        from geoacceptance.deepseek_launcher import main as launch
        with patch.dict(os.environ,{'GA_PROVIDER':'qwen','DASHSCOPE_API_KEY':'qwen-unit-placeholder','GA_API_KEY':'other-provider-placeholder'},clear=True):
            cfg=ModelConfig.from_env()
        self.assertEqual(cfg.api_key,'qwen-unit-placeholder')
        self.assertEqual(cfg.model,'qwen-plus')
        self.assertEqual(cfg.monetary(),(0.8,2.0,0.5))
        payloads=[]
        def transport(payload):
            payloads.append(payload)
            return {'choices':[{'message':{'content':'{}'},'finish_reason':'stop'}],
                    'usage':{'prompt_tokens':100,'completion_tokens':200,'total_tokens':300}}
        client=CompatibleClient(cfg,transport);client.complete([{'role':'user','content':'JSON'}])
        self.assertFalse(payloads[0]['enable_thinking']);self.assertNotIn('thinking',payloads[0])
        self.assertAlmostEqual(client.calls[0]['cost'],.00048);self.assertIsNone(client.calls[0]['cost_usd'])
        for bad in (replace(cfg,base_url='https://example.com/compatible-mode/v1'),replace(cfg,api_key=''),
                    replace(cfg,model='qwen-max'),replace(cfg,thinking='enabled')):
            with self.assertRaises(ModelError):CompatibleClient(bad,lambda _:self.fail('Must not call provider')).complete([{'role':'user','content':'JSON'}])
        with self.assertRaises(ModelError):CompatibleClient(cfg,lambda _:self.fail('Must not cross pricing tier')).complete([{'role':'user','content':'字'*50000}])
        stream=io.StringIO()
        with patch.dict(os.environ,{'GA_API_KEY':'other-provider-placeholder'},clear=True),redirect_stdout(stream),patch('geoacceptance.deepseek_launcher.read_key_file',return_value=None):
            self.assertEqual(launch(['--check'],provider='qwen'),2)
        self.assertFalse(json.loads(stream.getvalue())['key_present'])
        self.assertEqual(json.loads(stream.getvalue())['provider'],'qwen')

    def test_provider_auth_failure_preserves_safe_status_without_retry(self):
        from unittest.mock import patch
        import urllib.error
        cfg=ModelConfig('https://api.deepseek.com','deepseek-flash','unit-credential',provider='deepseek',currency='CNY',
            input_price_per_million=2,output_price_per_million=8,job_budget=.5)
        class FakeOpener:
            count=0
            def open(self,*args,**kwargs):
                self.count+=1
                raise urllib.error.HTTPError('https://api.deepseek.com/chat/completions',401,'untrusted secret-provider-body',{},io.BytesIO(json.dumps({'error':{'code':'AccessDenied.Unpurchased','message':'unit-credential secret-provider-body'}}).encode()))
        opener=FakeOpener();client=CompatibleClient(cfg)
        with patch('urllib.request.build_opener',return_value=opener):
            with self.assertRaises(ModelError) as caught:client.complete([{'role':'user','content':'JSON'}])
        self.assertEqual(opener.count,1);self.assertEqual(len(client.calls),1)
        self.assertEqual(client.calls[0]['http_status'],401)
        self.assertEqual(client.calls[0]['error_code'],'PROVIDER_HTTP_ERROR')
        self.assertEqual(client.calls[0]['provider_code'],'AccessDenied.Unpurchased')
        self.assertNotIn('secret-provider-body',json.dumps(client.calls)+str(caught.exception))
        self.assertNotIn(cfg.api_key,json.dumps(client.calls)+str(caught.exception))

    def test_private_key_file_is_literal_and_not_distributed(self):
        from geoacceptance.deepseek_launcher import read_key_file
        from tools.release_check import files
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            f=Path(tmp)/'qwen.env'
            self.assertIsNone(read_key_file(f,'DASHSCOPE_API_KEY'))
            f.write_text('# local\nDASHSCOPE_API_KEY="unit-placeholder"\n',encoding='utf-8')
            self.assertEqual(read_key_file(f,'DASHSCOPE_API_KEY'),'unit-placeholder')
            self.assertNotIn(f,[p for p,_ in files()])
            for text in ('OTHER=do-not-echo', 'DASHSCOPE_API_KEY=a\nDASHSCOPE_API_KEY=b', 'DASHSCOPE_API_KEY=a b'):
                f.write_text(text,encoding='utf-8')
                with self.assertRaises(ModelError) as caught:read_key_file(f,'DASHSCOPE_API_KEY')
                self.assertNotIn('do-not-echo',str(caught.exception))

    def test_local_provider_never_uses_cloud_credentials(self):
        from unittest.mock import patch
        from dataclasses import replace
        from geoacceptance.local_launcher import local_env
        with patch.dict(os.environ,{'GA_PROVIDER':'ollama','GA_API_KEY':'foreign-key','DASHSCOPE_API_KEY':'another-key'},clear=True):
            cfg=ModelConfig.from_env()
        self.assertEqual(cfg.api_key,'');self.assertEqual(cfg.monetary(),(0,0,0));self.assertTrue(cfg.public()['configured'])
        payloads=[]
        client=CompatibleClient(cfg,lambda payload:(payloads.append(payload) or {'choices':[{'message':{'content':'{}'}}],
            'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}}))
        client.complete([{'role':'user','content':'JSON'}])
        self.assertEqual(payloads[0]['reasoning_effort'],'none');self.assertEqual(client.calls[0]['cost'],0)
        from geoacceptance.authoring import draft_output_schema
        client.complete([{'role':'user','content':'JSON'}],response_schema=draft_output_schema())
        self.assertEqual(payloads[-1]['response_format']['type'],'json_schema')
        self.assertEqual(payloads[-1]['response_format']['json_schema']['schema']['required'],['requirements','rules'])
        grounded=draft_output_schema(ROOT/'examples/clean')
        choices=grounded['properties']['requirements']['items']['anyOf']
        first=choices[0]['properties']
        self.assertEqual(first['requirement_id']['const'],'A1')
        lines=(ROOT/'examples/clean/delivery_spec.md').read_text(encoding='utf-8').splitlines()
        self.assertEqual(first['source_quote']['const'],lines[first['source_line_start']['const']-1])
        for bad in (replace(cfg,base_url='https://example.com/v1'),replace(cfg,api_key='foreign-key'),
                    replace(cfg,model='qwen3:4b-cloud'),replace(cfg,input_price_per_million=1)):
            with self.assertRaises(ModelError):CompatibleClient(bad,lambda _:self.fail('No remote calls')).complete([{'role':'user','content':'JSON'}])
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp,patch.dict(os.environ,{'GA_API_KEY':'foreign-key','DASHSCOPE_API_KEY':'another-key'}):
            env=local_env(Path(tmp));self.assertNotIn('GA_API_KEY',env);self.assertNotIn('DASHSCOPE_API_KEY',env)
            self.assertEqual(env['OLLAMA_NO_CLOUD'],'1');self.assertEqual(env['OLLAMA_NUM_PARALLEL'],'1')

    def test_live_case_scorer_catches_bad_parameters(self):
        from tools.live_acceptance import cases,assess
        case=cases()[0];draft=create_draft(ROOT/'examples/clean')
        self.assertTrue(all(assess(case,draft).values()))
        next(r for r in draft['rules'] if r['rule_type']=='freshness')['parameters']['max_age_days']=365
        self.assertFalse(assess(case,draft)['parameters:freshness'])
        self.assertEqual(len(cases()),12)

    def test_quality_scorer_rejects_observed_local_errors(self):
        from tools.live_acceptance import cases,assess,source_validation
        draft=create_draft(ROOT/'examples/clean');case=cases()[0]
        self.assertTrue(all(assess(case,draft).values()))
        draft['requirements'][-1]['required_for_release']=True
        next(r for r in draft['rules'] if r['rule_id']=='R02')['parameters']['trim']=None
        next(r for r in draft['rules'] if r['rule_id']=='R10')['parameters']['name_equal']=None
        checks=assess(case,draft)
        for key in ('advisory_not_mandatory','trim_whitespace','duplicate_name_condition'):self.assertFalse(checks[key])
        draft=create_draft(ROOT/'examples/clean')
        before=copy.deepcopy(draft)
        self.assertFalse(source_validation(ROOT/'examples/clean',draft)['quote_and_parameter_problems'])
        self.assertEqual(draft,before)
        next(r for r in draft['rules'] if r['rule_id']=='R08')['parameter_sources'][0]['value_literal']=['inclusive']
        self.assertTrue(source_validation(ROOT/'examples/clean',draft)['quote_and_parameter_problems'])
        self.assertTrue(all(r['status']=='DRAFT' for r in draft['rules']))

    def test_local_output_schema_is_valid_and_preserves_contract_bounds(self):
        import jsonschema
        from geoacceptance.authoring import draft_output_schema
        schema=draft_output_schema(ROOT/'examples/clean')
        jsonschema.Draft202012Validator.check_schema(schema)
        variants=schema['properties']['rules']['items']['anyOf']
        for r in variants:
            typ=r['properties']['rule_type']['const']
            if typ=='non_empty':
                params=r['properties']['parameters']
                jsonschema.validate({'fields':['name'],'trim':True,'missing_rate_policy':'STRICT'},params)
                with self.assertRaises(jsonschema.ValidationError):jsonschema.validate({'fields':['name'],'trim':None,'missing_rate_policy':'STRICT'},params)
            if typ=='within_project_area':
                source_schema=r['properties']['parameter_sources']['items']
                src=copy.deepcopy(manual_proposal(ROOT/'examples/clean')['rules'][7]['parameter_sources'][0])
                for k in ('document_id','document_sha256'):src.pop(k)
                jsonschema.validate(src,source_schema)
                src['parameter']='fields'
                with self.assertRaises(jsonschema.ValidationError):jsonschema.validate(src,source_schema)

    def test_local_evidence_compiler_preserves_values_and_quarantines_invalid_rules(self):
        from geoacceptance.local_authoring import compile_proposal,output_schema,SOURCE_PARAMS
        import jsonschema
        bundle=ROOT/'examples/clean';raw=manual_proposal(bundle)
        for rule in raw['rules']:
            sources=rule.pop('parameter_sources')
            rule['parameter_evidence']={}
            for source in sources:
                name=source['parameter']
                proof={k:source[k] for k in ('requirement_id','source_line_start','source_line_end','source_quote','interpretation')}
                if name=='boundary_policy':proof['value_literal']=source['value_literal']
                rule['parameter_evidence'][name]=proof
        jsonschema.Draft202012Validator.check_schema(output_schema(bundle))
        before=copy.deepcopy(raw);compiled=compile_proposal(raw,bundle)
        self.assertEqual(raw,before);self.assertEqual(len(compiled['rules']),10)
        self.assertFalse(compiled['compiler']['quarantined_rules'])
        from tools.live_acceptance import source_validation
        self.assertFalse(source_validation(bundle,compiled)['quote_and_parameter_problems'])
        next(r for r in raw['rules'] if r['rule_type']=='freshness')['parameters']['max_age_days']=365
        compiled=compile_proposal(raw,bundle)
        # The compiler never replaces the invented parameter with the fixture's 30.
        self.assertFalse(any(r['rule_id']=='R09' for r in compiled['rules']))
        self.assertEqual(next(r for r in raw['rules'] if r['rule_type']=='freshness')['parameters']['max_age_days'],365)
        self.assertTrue(compiled['compiler']['quarantined_rules'])
        next(r for r in raw['rules'] if r['rule_type']=='freshness')['parameters']['reference_time']=''
        compiled=compile_proposal(raw,bundle)
        self.assertFalse(any(r['rule_id']=='R09' for r in compiled['rules']))
        self.assertTrue(compiled['compiler']['quarantined_rules'])
        self.assertEqual(next(q for q in compiled['requirements'] if q['requirement_id']=='C1')['support_status'],'NEEDS_CLARIFICATION')
        self.assertTrue(all(r['status']=='DRAFT' for r in compiled['rules']))

    def test_loopback_transport_bypasses_proxy_environment(self):
        from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
        from unittest.mock import patch
        class Fixture(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                payload=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                assert payload['model']=='transport-fixture'
                data=json.dumps({'choices':[{'message':{'content':'{"ok":true}'}}]}).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        server=ThreadingHTTPServer(('127.0.0.1',0),Fixture)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            cfg=ModelConfig(base_url='http://127.0.0.1:'+str(server.server_port),model='transport-fixture',
                input_usd_per_million=0,output_usd_per_million=0,budget_usd=0)
            with patch.dict(os.environ,{'HTTP_PROXY':'http://127.0.0.1:9','HTTPS_PROXY':'http://127.0.0.1:9','NO_PROXY':''}):
                self.assertEqual(CompatibleClient(cfg).complete([{'role':'user','content':'fixture only'}]),{'ok':True})
        finally:server.shutdown();server.server_close();thread.join()

    def test_kernel_package_import_has_no_script_path_dependency(self):
        import subprocess
        result=subprocess.run([sys.executable,'-X','utf8','-c',
            "from pathlib import Path; from tools.stage0_gate import Kernel; k=Kernel(Path('examples/clean')); assert not k.collect_config_rejections(); print('PACKAGE_IMPORT_OK')"],
            cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(result.returncode,0,result.stderr);self.assertIn('PACKAGE_IMPORT_OK',result.stdout)

    def test_unconfigured_live_fails_honestly(self):
        with self.assertRaises(ModelError):CompatibleClient(ModelConfig()).complete([{'role':'user','content':'x'}])
    def test_restart_marks_running_interrupted(self):
        with self.s.connect() as c:c.execute("INSERT INTO jobs(id,project,kind,revision,status,result,error,created,idempotency) VALUES('dead','p','draft',1,'RUNNING',NULL,NULL,'now','dead')")
        self.s.close()
        s2=Service(self.s.root)
        with s2.connect() as c:self.assertEqual(c.execute("SELECT status FROM jobs WHERE id='dead'").fetchone()[0],'INTERRUPTED')
        s2.close()
    def test_storage_owner_is_exclusive(self):
        with self.assertRaises(Conflict):Service(self.s.root)
    def test_crlf_source_hash_is_raw_bytes(self):
        files={n:(ROOT/'examples'/'clean'/n).read_text(encoding='utf-8') for n in INPUTS}
        files['delivery_spec.md']=files['delivery_spec.md'].replace('\n','\r\n')
        p=self.s.create('CRLF',files);wait(self.s,self.s.submit(p['id'],'draft',p['revision'],'draft'))
        p=self.s.detail(p['id']);raw_hash=hashlib.sha256((self.s.path(p['id'])/'delivery_spec.md').read_bytes()).hexdigest()
        self.assertEqual(p['draft']['requirements'][0]['document_sha256'],raw_hash)
        self.s.approve(p['id'],p['revision'],p['draft'],'A')
    def test_failed_draft_does_not_erase_previous_approval(self):
        p=self.approved();j=wait(self.s,self.s.submit(p['id'],'draft',p['revision'],'unconfigured-live','live'))
        self.assertEqual(j['status'],'FAILED');self.assertTrue(self.s.project(p['id'])['approval'])
    def test_omitted_model_requirements_preserved_as_unknown(self):
        b=ROOT/'examples'/'clean';raw=manual_proposal(b);raw['requirements']=raw['requirements'][1:];raw['rules']=raw['rules'][1:]
        n=normalize_proposal(raw,b)
        self.assertTrue(any(q['requirement_id'].startswith('MISSING_') and q['support_status']=='UNSUPPORTED' for q in n['requirements']))
    def test_reproposal_invalidates_old_approval(self):
        p=self.approved();wait(self.s,self.s.submit(p['id'],'draft',p['revision'],'new-draft'))
        q=self.s.project(p['id']);self.assertIsNone(q['approval'])
        with self.assertRaises(Conflict):self.s.submit(q['id'],'validate',q['revision'],'bad-run')
    def test_path_upload_rejected(self):
        with self.assertRaises(ValueError):self.s.create('bad',{'../secret':'x'})

class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'work');self.server=AppServer(0,self.tmp.name)
        self.t=threading.Thread(target=self.server.serve_forever,daemon=True);self.t.start();self.base='http://127.0.0.1:'+str(self.server.server_port)
    def tearDown(self):self.server.shutdown();self.server.server_close();self.server.service.close();self.tmp.cleanup()
    def request(self,path,data=None,csrf=None,origin=None):
        h={}
        if data is not None:h.update({'Content-Type':'application/json','X-CSRF-Token':csrf or ''})
        if origin:h['Origin']=origin
        req=urllib.request.Request(self.base+path,json.dumps(data).encode() if data is not None else None,h)
        with urllib.request.urlopen(req) as r:return r.status,r.read().decode()
    def test_http_security_and_api(self):
        code,page=self.request('/');self.assertEqual(code,200);self.assertIn(self.server.csrf,page)
        with self.assertRaises(urllib.error.HTTPError) as e:self.request('/api/examples',{'name':'clean'})
        self.assertEqual(e.exception.code,403)
        with self.assertRaises(urllib.error.HTTPError):self.request('/api/examples',{'name':'clean'},self.server.csrf,'https://evil.example')
        code,raw=self.request('/api/examples',{'name':'clean'},self.server.csrf);self.assertEqual(code,201);p=json.loads(raw)
        code,raw=self.request('/api/projects/'+p['id']);self.assertIn('preview',json.loads(raw))

if __name__=='__main__':
    (ROOT/'work').mkdir(exist_ok=True);unittest.main(verbosity=2)


