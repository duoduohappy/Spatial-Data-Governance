"""Summarize developer-visible local quality runs without inference or approval."""
from __future__ import annotations
import json,datetime,statistics,sys,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.live_acceptance import assess,cases

def summarize(path):
    report=json.loads(path.read_text(encoding='utf-8'));expected={c['id']:c for c in cases()};rows=[]
    for row in report['cases']:
        checks=assess(expected[row['id']],row['draft']) if row.get('draft') else {}
        if row.get('source_validation'):
            checks['parameter_lineage']=not row['source_validation']['quote_and_parameter_problems']
            if row['id'].startswith('clear-'):checks['configuration_valid']=not row['source_validation']['configuration_rejections']
        passed=bool(checks) and all(checks.values())
        safe_rejection=bool(row.get('guard_expected')) and row['status']=='GUARD_REJECTED'
        rows.append({'id':row['id'],'status':'AUTOMATED_CHECKS_PASS_REVIEW_PENDING' if passed else 'EXPECTED_GUARD_REJECTION' if safe_rejection else 'FAIL',
            'checks':checks,'failed_checks':[k for k,v in checks.items() if not v],'error':row.get('error'),
            'source_problems':row.get('source_validation',{}).get('quote_and_parameter_problems',[]),
            'configuration_rejections':row.get('source_validation',{}).get('configuration_rejections',[]),
            'duration_ms':row.get('duration_ms'),'human_review':row.get('human_review'),'quarantined_rules':row.get('draft',{}).get('compiler',{}).get('quarantined_rules',[])})
    calls=[call for row in report['cases'] for call in row.get('calls',[])]
    return {'source':str(path.relative_to(ROOT)), 'run_status':report['status'],'cases':rows,'check_totals':{key:{'pass':sum(r['checks'].get(key) is True for r in rows),'total':sum(key in r['checks'] for r in rows)} for key in sorted({k for r in rows for k in r['checks']})},
        'passed_checks':sum(r['status']=='AUTOMATED_CHECKS_PASS_REVIEW_PENDING' for r in rows),
        'expected_guard_rejections':sum(r['status']=='EXPECTED_GUARD_REJECTION' for r in rows),
        'failed':sum(r['status']=='FAIL' for r in rows),'calls':len(calls),
        'reported_total_tokens':sum(c['usage']['total_tokens'] for c in calls if c.get('usage') and type(c['usage'].get('total_tokens')) is int),
        'missing_usage_calls':sum(not c.get('usage') for c in calls),
        'latency_median_ms':statistics.median([r['duration_ms'] for r in rows if r['duration_ms'] is not None]) if rows else None}

def main():
    runs=[]
    for path in sorted((ROOT/'acceptance/stage-4/local-model').glob('quality-v[0-9]*/results.json'),key=lambda p:int(re.search(r'quality-v(\d+)',str(p)).group(1))):
        runs.append(summarize(path))
    data={'at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'kind':'DEVELOPER_VISIBLE_REGRESSION_NOT_BLIND_EVALUATION',
          'scope':'Same synthetic templates before/after contract-guided tuning; no automatic approval, independent human acceptance, multi-agent experiment or ROI claim.',
          'comparison':'All stored drafts rescored by the current common scorer; original per-run results remain unchanged.','runs':runs}
    out=ROOT/'acceptance/stage-4/local-model/quality-summary.json';out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 本地模型质量检查记录','','本报告是开发者可见的合成样例回归，不是盲测、客户效果或独立验收。模型只生成待审核草案，测试没有批准项目。各轮原始输出均保留，使用当前同一检查器重评；后续版本根据已暴露问题修改了提示词、结构约束和证据编译器，因此不用于宣称模型泛化提升。','',
        '## 执行结果','','| 版本 | 已完成样例 | 自动检查通过、待复核 | 预期护栏拒绝 | 未通过 | Token（接口报告） |','|---|---:|---:|---:|---:|---:|']
    for run in runs:
        name=Path(run['source']).parent.name
        lines.append(f"| {name} | {len(run['cases'])} | {run['passed_checks']} | {run['expected_guard_rejections']} | {run['failed']} | {run['reported_total_tokens']} |")
    lines+=['','所有调用均为 loopback Ollama/Qwen3 4B，本轮没有云端 API 调用。未通过不能记作可直接批准；通过自动检查也仍需审核原文和参数。','',
        '## 分项结果','','| 检查 | 版本 | 通过 / 执行 |','|---|---|---|']
    for run in runs:
        for key,count in run['check_totals'].items():lines.append(f"| {key} | {Path(run['source']).parent.name} | {count['pass']} / {count['total']} |")
    lines+=['','## 逐例结论','','| 版本 | 样例 | 结论 | 失败检查 |','|---|---|---|---|']
    for run in runs:
        for row in run['cases']:lines.append(f"| {Path(run['source']).parent.name} | {row['id']} | {row['status']} | {', '.join(row['failed_checks']) or row.get('error') or '-'} |")
    lines+=['','第 4 轮的自动通过包含证据编译器对无依据规则的隔离，不等于模型原始输出零错误。被隔离的规则和原因保存在每例 draft.compiler.quarantined_rules；对应条款保留待澄清，程序不替模型补参数。第 3 轮因 Codex 重启中断，仅保留 11 个已完成样例。','','## 使用边界','','依据 docs/evaluation.md §4，未达原始目标时降级为逐条人工确认的实验版本。当前回归没有提供达到独立条款 F1 / 完整映射正确率 ≥ 0.90 的证据；自动检查通过比例不是这两个指标。','','当前应作为“模型建议＋人工审核＋确定性检查”的工作台使用。不能省去人工审核、宣称零幻觉、模型自动验收或多智能体优越。结构约束能限制可引用原文和来源格式，不能证明模型理解了条款。候选分句仍有识别范围限制。',
        '', '精确输入、输出 Schema、调用用量、原始草案、错误和检查结果在 acceptance/stage-4/local-model/quality-v1 至 quality-v4；各自 experiment.json 记录提示词和源码摘要。quality-summary.json 是可复现的共同重评结果。重评命令：python tools/summarize_local_quality.py。',
        '', '后续验收：独立业务标注与复核者；真实用户审核耗时；Docker 与 GitHub CI。开发留出集和内置浏览器实际附件保存已完成，见后文及 stage-3/iab-downloads；暂无真实多 Agent 对照或业务收益数据。']
    heldout_path=ROOT/'acceptance/stage-4/local-model/heldout-v1/results.json'
    if heldout_path.exists():
        heldout=json.loads(heldout_path.read_text(encoding='utf-8'));m=heldout['metrics']
        lines+=['','## 冻结后新表述检查','',
            '8 份新说明、80 条原子要求，推理前冻结文档、开发标签和提示词摘要；未将预期标签发送给模型。标签由实现方 Codex 制作，不是独立人工金标准，不称为盲测。',
            '',f"状态：{heldout['status']}。原始语义匹配 {m['raw_semantics_correct']}/{m['clauses']}；编译后完整规则映射 {m['compiled_semantics_correct']}/{m['clauses']}（{m['compiled_complete_rule_mapping']:.2%}）；覆盖 {m['covered']}/{m['clauses']}；缺失信息条款分类错误 {m['unknown_clause_errors']}；来源问题 {m['lineage_problems']}。所有草案均未自动批准。",
            '', '原始语义匹配只检查直接条款、支持状态、字段、条件和参数；执行依赖由确定性程序建立，不是模型生成的成绩。覆盖受候选分句约束，不能当作自由提取 F1。组合管线的门槛在推理前固定为映射至少 0.90、覆盖完整、未知误判与来源问题为零。',
            '', '仍未完整映射的条款：']
        for case in heldout['cases']:
            bad=[row['rule_type'] for row in case.get('scores',[]) if not row['compiled_semantics_correct']]
            if bad:lines.append('- '+case['id']+'：'+', '.join(bad))
        lines+=['', '无来源的模型参数被隔离为未知，不替换成正确参数。原始输出、编译结果和隔离原因均保留于 heldout-v1。达到开发检查门槛，不代表独立业务验收已通过。']
    (ROOT/'docs/LOCAL_MODEL_QUALITY.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({Path(r['source']).parent.name:{'pass':r['passed_checks'],'guard':r['expected_guard_rejections'],'fail':r['failed'],'cases':len(r['cases'])} for r in runs}))
if __name__=='__main__':main()
