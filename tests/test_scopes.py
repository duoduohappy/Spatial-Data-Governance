"""Scope identity, eligibility and remediation tests against the real service/kernel."""
import copy,csv,io,json,sys,tempfile,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from geoacceptance.service import Service,INPUTS
from geoacceptance.authoring import create_draft,normalize_proposal
from geoacceptance.compare import _rule_fingerprint
ROOT=Path(__file__).resolve().parents[1]
def wait(service,job):
    for _ in range(1000):
        row=service.job(job['id'])
        if row['status'] not in ('QUEUED','RUNNING'):
            assert row['status']=='COMPLETED',row.get('error');return row
        time.sleep(.01)
    raise AssertionError('Timeout')
class ScopeTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory(dir=ROOT/'work');self.s=Service(Path(self.tmp.name))
    def tearDown(self):self.s.close();self.tmp.cleanup()
    def project(self):
        p=self.s.example('scoped_sources');wait(self.s,self.s.submit(p['id'],'draft',1,'draft'));p=self.s.detail(p['id']);return self.s.approve(p['id'],p['revision'],p['draft'],'synthetic developer review')
    def run_project(self,p):return wait(self.s,self.s.submit(p['id'],'validate',p['revision'],'check'))
    def changed(self,p,fn):
        b=self.s.path(p['id']);reader=csv.DictReader(io.StringIO((b/'poi.csv').read_text(encoding='utf-8')));fields=reader.fieldnames;rows=list(reader);fn(rows)
        buffer=io.StringIO();writer=csv.DictWriter(buffer,fieldnames=fields);writer.writeheader();writer.writerows(rows)
        return self.s.corrected(p['id'],p['revision'],{'poi.csv':buffer.getvalue()},'scope test correction')
    def test_distinct_thresholds_and_instance_identity(self):
        p=self.project();result=self.run_project(p)['result'];self.assertEqual(result['aggregate_verdict'],'PASS')
        scoped=[r for r in result['check_results'] if r.get('scope')]
        self.assertEqual(len(scoped),2);self.assertEqual(len({r['rule_id'] for r in scoped}),2)
        self.assertEqual([r['summary_counts']['records_total'] for r in scoped],[1,1])
        self.assertEqual({r['scope']['equals'] for r in scoped},{'municipal','survey'})
    def test_stale_municipal_does_not_apply_seven_days_to_survey(self):
        p=self.project();bad=self.changed(p,lambda rows:rows[0].update(source_time='2026-09-10T00:00:00Z'));result=self.run_project(bad)['result']
        self.assertEqual(result['aggregate_verdict'],'FAIL');scoped={r['scope']['equals']:r for r in result['check_results'] if r.get('scope')}
        self.assertEqual(scoped['municipal']['verdict'],'FAIL');self.assertEqual(scoped['survey']['verdict'],'PASS')
        findings=[f for f in result['findings'] if f['reason_code']=='STALE_RECORD'];self.assertEqual(len(findings),1);self.assertEqual(findings[0]['rule_id'],scoped['municipal']['rule_id'])
    def test_unknown_source_cannot_disappear_from_eligibility(self):
        p=self.project();bad=self.changed(p,lambda rows:rows[0].update(source='unregistered'));result=self.run_project(bad)['result']
        self.assertEqual(result['aggregate_verdict'],'INDETERMINATE')
        self.assertTrue(all(r['scope_selection']['unknown_selector_records']==1 for r in result['check_results'] if r.get('scope')))
    def test_zero_matching_population_is_not_pass(self):
        p=self.project();empty=self.changed(p,lambda rows:rows[0].update(source='survey'));result=self.run_project(empty)['result']
        self.assertEqual(result['aggregate_verdict'],'INDETERMINATE')
        municipal=next(r for r in result['check_results'] if r.get('scope',{}).get('equals')=='municipal')
        self.assertEqual(municipal['summary_counts']['records_evaluated'],0);self.assertNotEqual(municipal['verdict'],'PASS')
    def test_scope_changes_are_part_of_the_ruler(self):
        p=self.project();rules=p['approval']['rules_doc']['rules'];rule=next(r for r in rules if r.get('scope'));changed=copy.deepcopy(rule);changed['scope']['equals']='other'
        self.assertNotEqual(_rule_fingerprint(rule),_rule_fingerprint(changed))
    def test_real_remediation_closes_only_same_scoped_instance(self):
        p=self.project();bad=self.changed(p,lambda rows:rows[0].update(source_time='2026-09-10T00:00:00Z'));before=self.run_project(bad)
        fixed=self.changed(bad,lambda rows:rows[0].update(source_time='2026-09-28T00:00:00Z'));after=self.run_project(fixed);comparison=self.s.compare(before['id'],after['id'])
        self.assertEqual(comparison['overall'],'LEDGER_CLOSED_ACCEPTED');self.assertEqual(comparison['counts']['closed'],1)
    def test_normalizer_rejects_inferred_or_overlapping_scope(self):
        b=ROOT/'examples/scoped_sources';draft=create_draft(b);rules=[r for r in draft['rules'] if r.get('scope')]
        for mutation in ['unknown_field','alias','omit','wrong_clause','overlap','null','wrong_type']:
            changed=copy.deepcopy(draft);scoped=[r for r in changed['rules'] if r.get('scope')]
            if mutation=='unknown_field':scoped[0]['scope']['field']='missing'
            if mutation=='alias':scoped[0]['scope']['equals']='municipal '
            if mutation=='omit':scoped[0].pop('scope')
            if mutation=='wrong_clause':scoped[0]['scope']['requirement_id']='A1'
            if mutation=='overlap':scoped[1]['scope']=copy.deepcopy(scoped[0]['scope'])
            if mutation=='null':scoped[0]['scope']=None
            if mutation=='wrong_type':scoped[0]['scope']['field']=[]
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):normalize_proposal(changed,b)
    def test_reclassification_cannot_close_a_failure(self):
        p=self.project()
        def old(rows):
            rows.append(dict(rows[0],record_id='M-002',name='合成另一个市政设施'))
            rows[0]['source_time']='2026-09-10T00:00:00Z'
        bad=self.changed(p,old);before=self.run_project(bad)
        moved=self.changed(bad,lambda rows:rows[0].update(source='survey'));after=self.run_project(moved)
        self.assertEqual(after['result']['aggregate_verdict'],'PASS')
        comparison=self.s.compare(before['id'],after['id'])
        self.assertEqual(comparison['overall'],'LEDGER_INDETERMINATE')
        self.assertFalse(any(i['record_id']=='M-001' and i['status']=='closed' for i in comparison['items']))
        self.assertTrue(any(i.get('selector_changes') for i in comparison['items']))
    def test_negated_selector_is_not_inferred_as_positive(self):
        from tools.rule_scopes import parse_scope
        self.assertIsNone(parse_scope('C1. 并非仅对 source="municipal" 的记录适用规则。','C1'))
    def test_scoped_output_schema_forbids_unscoped_conditional_rules(self):
        import jsonschema
        from geoacceptance.local_authoring import output_schema
        schema=output_schema(ROOT/'examples/scoped_sources');jsonschema.Draft202012Validator.check_schema(schema)
        fresh=[v for v in schema['properties']['rules']['items']['anyOf'] if v['properties']['rule_type']['const']=='freshness']
        self.assertEqual(len(fresh),2)
        for variant in fresh:
            self.assertIn('scope',variant['required']);self.assertIn('const',variant['properties']['requirement_ids'])
    def test_html_report_retains_scope_and_escapes_values(self):
        from geoacceptance.reporting import render_html
        text=render_html({'check_results':[{'rule_id':'test','scope':{'field':'source','equals':'<img src=x>'},'summary_counts':{}}]})
        self.assertIn('source=&lt;img src=x&gt;',text);self.assertNotIn('<img src=x>',text)
    def test_reordering_proposals_does_not_change_identity(self):
        b=ROOT/'examples/scoped_sources';draft=create_draft(b);old={r['rule_id'] for r in draft['rules']};changed=copy.deepcopy(draft);changed['rules'].reverse()
        self.assertEqual(old,{r['rule_id'] for r in normalize_proposal(changed,b)['rules']})
if __name__=='__main__':unittest.main(verbosity=2)
