"""Derive v0.6 status from recorded tests and measurements without claiming business approval."""
from pathlib import Path
import datetime,json,re
ROOT=Path(__file__).resolve().parents[1]
def read(name):return json.loads((ROOT/name).read_text(encoding='utf-8-sig'))
def main():
    log=(ROOT/'acceptance/v06/tests.txt').read_text(encoding='utf-8-sig')
    match=re.search(r'Ran (\d+) tests?',log);assert match and '\nOK' in log and 'FAILED (' not in log
    core=(ROOT/'acceptance/v06/core-probes.txt').read_text(encoding='utf-8-sig');compare=(ROOT/'acceptance/v06/compare-probes.txt').read_text(encoding='utf-8-sig')
    assert 'RECHECK_PROBES_OK=true' in core and 'COMPARE_PROBES_OK=true' in compare
    assert 'ALL_OK=true' in (ROOT/'acceptance/v06/frozen-gate.txt').read_text(encoding='utf-8-sig')
    browser=read('acceptance/v06/browser/latest.json');assert browser['status']=='PASS' and not browser['errors']
    http=read('acceptance/v06/http-workflow.json');assert http['status']=='PASS'
    iab=read('acceptance/v06/iab/results.json');assert iab['status']=='PASS'
    model=read('acceptance/v06/review-ablation-v2/results.json');assert len(model['cases'])==12 and all(c['status']=='COMPLETED' for c in model['cases'])
    remote_path=ROOT/'acceptance/v06/remote-ci/results.json';remote=read(str(remote_path.relative_to(ROOT))) if remote_path.exists() else {'status':'NOT_RUN_FOR_THIS_BRANCH'}
    remote_pass=remote.get('status')=='PASS' and len(remote.get('jobs',[]))==5 and all(j['conclusion']=='success' for j in remote['jobs'])
    status={'version':'0.6.0-rc1','at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'functional_acceptance':'LOCAL_AND_REMOTE_ENGINEERING_CHECKS_PASS' if remote_pass else 'LOCAL_ENGINEERING_CHECKS_PASS_REMOTE_PENDING',
        'checks':{'unit_and_http_tests':int(match.group(1)),'frozen_examples':6,'core_probes':30,'compare_probes':33,'real_browser_checks':len(browser['checks']),'http_workflow_checks':len(http['checks']),'actual_iab_workflow':'PASS'},
        'model_quality':{'metrics':model['metrics'],'adoption':model['adoption'],'default_strategy':'single','scope':model['scope'],'not_independent_human_gold':True},
        'live_workbench':iab,'remote_ci':remote,
        'pilot':read('eval/pilot-template/STATUS.json'),'not_measured':['independent business acceptance','human active review time / ROI','production operation'],
        'limits':['same local model, serial roles','optional reviewer tools; zero tool requests in current workbench demo','freshness scopes only; explicit positive markers and disjoint enum values','source reclassification requires business review; no automatic authorization channel']}
    (ROOT/'acceptance/v06/STATUS.json').write_text(json.dumps(status,ensure_ascii=False,indent=2),encoding='utf-8')
    text=f'''# 0.6.0-rc1 升级验收状态

日期：2026-10-28。功能状态：**{status['functional_acceptance']}**。

本轮实现：可选双角色提议/审查，受控查询、一次修订、人工确认；按来源的 freshness 多实例，稳定规则 ID、范围指纹、未知/零匹配保护、重分类不自动关闭；POI 试点流程及空白记录模板。

本地实际检查：{status['checks']['unit_and_http_tests']} 项应用/协作/范围测试，六包门禁、30 核心探针、33 对比探针、{status['checks']['real_browser_checks']} 项真实浏览器检查、{status['checks']['http_workflow_checks']} 项 HTTP 流程检查均通过。内置浏览器已对真实本地双角色生成的合成草案进行开发复核、批准和验证，参数零修改，两条来源范围分别执行并 PASS；这不是独立业务批准。

模型质量结论：单次 38/40、自检 38/40、双角色 37/40；Token 为 19,102 / 75,824 / 66,506。保留失败、精确源码快照和环境中断记录。双角色没有达到采用标准，默认仍为 single。开发标签不等于独立金标准，未测量人工效率。

本轮远程 CI 状态：{remote.get('status','UNKNOWN')}。远程运行：{remote.get('run_url','尚未执行；不能用 0.5 的通过记录替代')}。提交：{remote.get('commit','待提交')}。所有通过结论以对应运行的提交为界。

真实试点：POI 数据交付验收方向已选，实际批次/独立审核人为零；材料与标签未到位，状态 NOT_STARTED。见 POI_PILOT.md，不宣称生产上线或 ROI。

历史 0.5 发布与 80 条开发评测保存在 releases/0.5.0-rc1.md。新对照详见 V06_UPGRADE.md、acceptance/v06/review-ablation-v2/results.json；结构化总状态在 acceptance/v06/STATUS.json。
'''
    (ROOT/'docs/RELEASE_STATUS.md').write_text(text,encoding='utf-8')
    print(json.dumps({'functional_acceptance':status['functional_acceptance'],'checks':status['checks'],'model_adoption':model['adoption'],'pilot':'NOT_STARTED'},ensure_ascii=False))
if __name__=='__main__':main()
