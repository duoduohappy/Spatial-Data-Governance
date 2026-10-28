"""Adversarial collaboration contracts; scripted provider outputs, not live model evidence."""
import copy,json,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from geoacceptance.authoring import manual_proposal,create_draft
from geoacceptance.collaboration import create_collaborative_draft,read_tool,validate_review
from geoacceptance.llm import CompatibleClient,ModelConfig,ModelError
from geoacceptance.service import Service,Conflict
ROOT=Path(__file__).resolve().parents[1]
def raw_fixture(bundle):
    raw=manual_proposal(bundle)
    for rule in raw['rules']:
        evidence={}
        for source in rule.pop('parameter_sources',[]):
            name=source['parameter'];ev={k:source[k] for k in ('requirement_id','source_line_start','source_line_end','source_quote','interpretation')}
            if name=='boundary_policy':ev['value_literal']=source['value_literal']
            evidence[name]=ev
        rule['parameter_evidence']=evidence
    return raw
class CollaborationTests(unittest.TestCase):
    def setUp(self):
        self.bundle=ROOT/'examples/clean';self.raw=raw_fixture(self.bundle)
        self.draft=create_draft(self.bundle)
    def report(self,issues=None):
        issues=issues or {}
        return {'action':'FINAL','requests':[],'checks':[{'requirement_id':q['requirement_id'],'source_quote':q['source_quote'],'status':issues.get(q['requirement_id'],'CONFIRMED'),'reason':'Original source and proposal checked'} for q in self.draft['requirements']]}
    def client(self,outputs,seen=None):
        remaining=copy.deepcopy(outputs)
        def transport(payload):
            if seen is not None:seen.append(payload)
            return {'choices':[{'message':{'content':json.dumps(remaining.pop(0),ensure_ascii=False)},'finish_reason':'stop'}],'usage':{'prompt_tokens':10,'completion_tokens':20,'total_tokens':30}}
        return CompatibleClient(ModelConfig(provider='ollama',base_url='http://127.0.0.1:11434/v1',model='geoacceptance-qwen3:4b',currency='CNY',input_price_per_million=0,output_price_per_million=0,job_budget=0,max_calls=1,max_output_tokens=8192),transport)
    def test_separate_context_no_approval(self):
        seen=[];client=self.client([self.raw,self.report()],seen)
        draft=create_collaborative_draft(self.bundle,client)
        self.assertEqual(len(client.calls),2);self.assertEqual(len(seen[1]['messages']),2)
        self.assertTrue(all(r['status']=='DRAFT' and not r['reviewer'] for r in draft['rules']))
        self.assertIn('original_material',seen[1]['messages'][1]['content'])
        self.assertNotIn('SD-0001',seen[1]['messages'][1]['content'])
    def test_self_review_retains_authoring_context(self):
        seen=[];create_collaborative_draft(self.bundle,self.client([self.raw,self.report()],seen),'self_review')
        self.assertEqual(seen[1]['messages'][2]['role'],'assistant')
    def test_tool_round_and_single_revision_bounded(self):
        bad=copy.deepcopy(self.raw);next(r for r in bad['rules'] if r['rule_type']=='non_empty')['parameters']['trim']=False
        tools={'action':'TOOLS','requests':[{'name':'inspect_dictionary','argument':'name'}],'checks':[]}
        cid=next(r for r in self.draft['rules'] if r['rule_type']=='non_empty')['requirement_ids'][0]
        client=self.client([bad,tools,self.report({cid:'ISSUE'}),self.raw])
        draft=create_collaborative_draft(self.bundle,client)
        self.assertEqual(len(client.calls),4);self.assertEqual(len(draft['collaboration']['tool_trace']),1)
        self.assertTrue(next(r for r in draft['rules'] if r['rule_type']=='non_empty')['parameters']['trim'])
        self.assertEqual(draft['collaboration']['revision']['status'],'REVISED_REQUIRES_HUMAN_CONFIRMATION')
    def test_unresolved_without_revision_remains_unknown(self):
        cid=self.draft['requirements'][0]['requirement_id'];draft=create_collaborative_draft(self.bundle,self.client([self.raw,self.report({cid:'NEEDS_CLARIFICATION'})]),revise=False)
        self.assertFalse(any(cid in r['requirement_ids'] for r in draft['rules']))
        self.assertEqual(draft['requirements'][0]['support_status'],'NEEDS_CLARIFICATION')
    def test_review_requires_complete_exact_evidence(self):
        report=self.report();report['checks'].pop()
        with self.assertRaises(ValueError):validate_review(report,self.draft)
        report=self.report();report['checks'][0]['source_quote']='invented'
        with self.assertRaises(ValueError):validate_review(report,self.draft)
        report=self.report();report['checks'][0]['status']='APPROVED'
        with self.assertRaises(ValueError):validate_review(report,self.draft)
    def test_keyed_review_compiles_without_omitting_ids(self):
        report=self.report();report['checks']={c['requirement_id']:{k:v for k,v in c.items() if k!='requirement_id'} for c in report['checks']}
        self.assertEqual(len(validate_review(report,self.draft)['checks']),len(self.draft['requirements']))
    def test_compiler_rejected_evidence_can_be_revised_without_changing_truth(self):
        bad=copy.deepcopy(self.raw);rule=next(r for r in bad['rules'] if r['rule_type']=='freshness');rule['parameters']['max_age_days']=999
        cid=rule['requirement_ids'][0]
        draft=create_collaborative_draft(self.bundle,self.client([bad,self.report({cid:'ISSUE'}),self.raw]))
        self.assertEqual(next(r for r in draft['rules'] if r['rule_type']=='freshness')['parameters']['max_age_days'],30)
        self.assertTrue(draft['collaboration']['revision'])
    def test_tools_cannot_escape_read_only_boundary(self):
        from geoacceptance.authoring import outbound_preview
        preview=outbound_preview(self.bundle)
        for request in [{'name':'approve','argument':'all'},{'name':'read_source_lines','argument':'../../private/qwen.env'},{'name':'read_source_lines','argument':'1:9999'},{'name':'inspect_dictionary','argument':'record-values'}]:
            with self.assertRaises(ValueError):read_tool(preview,request)
    def test_second_tool_round_is_rejected(self):
        request={'action':'TOOLS','requests':[{'name':'inspect_contract','argument':'freshness'}],'checks':[]}
        client=self.client([self.raw,request,request])
        with self.assertRaises(ValueError):create_collaborative_draft(self.bundle,client)
        self.assertEqual(len(client.calls),3)
    def test_cloud_rejected_before_any_call(self):
        client=self.client([]);client.config.provider='compatible'
        with self.assertRaises(ModelError):create_collaborative_draft(self.bundle,client)
        self.assertEqual(client.calls,[])
    def test_stored_collaboration_cannot_be_removed_to_bypass_ack(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            service=Service(Path(tmp))
            try:
                project=service.example('clean');draft=copy.deepcopy(self.draft);draft.update(mode='live',calls=[],collaboration={'strategy':'dual_review','revision':None})
                with service.connect() as con:con.execute('UPDATE projects SET draft=? WHERE id=?',(json.dumps(draft),project['id']))
                edited=copy.deepcopy(draft);edited.pop('collaboration')
                with self.assertRaises(ValueError):service.approve(project['id'],1,edited,'test')
                result=service.approve(project['id'],1,edited,'test',True)
                self.assertTrue(result['approval']['collaboration_ack'])
            finally:service.close()
    def test_legacy_database_mode_migration_preserves_uncertainty(self):
        import sqlite3
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            db=sqlite3.connect(Path(tmp)/'state.sqlite')
            db.execute('CREATE TABLE jobs(id TEXT PRIMARY KEY,project TEXT,kind TEXT,revision INTEGER,status TEXT,result TEXT,error TEXT,created TEXT,idempotency TEXT UNIQUE)')
            db.execute("INSERT INTO jobs VALUES('known','p','draft',1,'COMPLETED',?,NULL,'now','known')",(json.dumps({'mode':'live'}),))
            db.execute("INSERT INTO jobs VALUES('unknown','p','draft',1,'RUNNING',NULL,NULL,'now','unknown')");db.commit();db.close()
            service=Service(Path(tmp))
            try:
                with service.connect() as con:
                    self.assertEqual(con.execute("SELECT mode FROM jobs WHERE id='known'").fetchone()[0],'live')
                    row=con.execute("SELECT mode,status FROM jobs WHERE id='unknown'").fetchone()
                    self.assertEqual(tuple(row),('legacy_unknown','INTERRUPTED'))
            finally:service.close()
    def test_idempotency_key_includes_strategy_and_mode(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as tmp:
            service=Service(Path(tmp))
            try:
                project=service.example('clean')
                with patch.object(service.pool,'submit'):
                    first=service.submit(project['id'],'draft',1,'same','live','single')
                    self.assertEqual(first['id'],service.submit(project['id'],'draft',1,'same','live','single')['id'])
                    with self.assertRaises(Conflict):service.submit(project['id'],'draft',1,'same','live','dual_review')
                    with self.assertRaises(Conflict):service.submit(project['id'],'draft',1,'same','manual','single')
            finally:service.close()
if __name__=='__main__':unittest.main(verbosity=2)
