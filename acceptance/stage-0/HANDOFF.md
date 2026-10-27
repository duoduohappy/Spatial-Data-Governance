# Stage 0 交接说明

- 日期：2026-10-26
- 阶段：Stage 0（示例与语义地基），**未进入任何业务代码或全局开发**
- 执行方：WorkBuddy　｜　产品负责人：用户　｜　独立验收：Codex（由用户转交）
- 依据的项目文档：《空间数据交付验收助手：项目执行与验收方案 v1.0》
- 工作区：`C:\Users\TempAdmin\WorkBuddy\2026-10-26-13-17-35\geoacceptance`
- 仓库：本地 git，分支 `main`；Stage 0 内容提交 `570c1b7ae47ac3d5fd54b6a070c0b4fc1cbd889e`
  （尚未推送到远端；公开仓库在 Stage 5 发布候选时另行确认）

## 一、本阶段完成项

| 交付物 | 路径 | 说明 |
|---|---|---|
| 示例数据 5 组 | `examples/{clean,defective,corrected,ambiguous,blocked}` | 合成数据，含交付说明/字典/数据/范围/CRS/已批准规则/期望结果 |
| 输入哈希清单 | `examples/INPUT_MANIFEST.json` | 每个文件的 sha256 与字节数 |
| 规则语义 | `docs/rule-semantics.md` | R01–R10 的参数、前置、三态语义、边界与正反例 |
| 三态判定与聚合 | `docs/three-state-verdict.md` | 组合矩阵、记录级→规则级算法、总体聚合伪代码 |
| 数据对象结构 | `docs/data-model.md` + `schemas/*.json`（草案） | Requirement / Rule / CheckResult / Finding / RunManifest / AuditEvent |
| 架构 | `docs/architecture.md` | 分层、目录、mode 三值、关键不变量 |
| 架构决策 | `docs/adr/ADR-001 … ADR-009` | 含本轮补充的 ADR-005/006/007 |
| 威胁模型 | `docs/threat-model.md` | 含明确"不声称"清单 |
| 评测设计（未执行） | `docs/evaluation.md` | 数据集规划、A/B/C 对照、10 项指标 |
| 已知限制 | `docs/limitations.md` | 实现近似、范围限制、证据力度限制 |
| 数据许可清单 | `data/LICENSES.md` | Stage 0 全合成；真实公开数据的准入规则 |
| 端到端门禁 | `tools/stage0_gate.py` | 零第三方依赖，原文→条款→规则→执行→三态→报告→比对期望 |
| 护栏自检 | `tools/selfcheck_guards.py` | 4 个负面用例 |
| 依赖冒烟 | `tools/smoke_deps.py` | 只报告不安装 |
| 示例生成器 | `tools/make_examples.py` | 确定性生成，引用行号回算后冻结 |

## 二、运行方式（干净环境）

```bash
cd geoacceptance
python tools/make_examples.py       # 可选：重新生成示例（会刷新 INPUT_MANIFEST.json）
python tools/stage0_gate.py         # 端到端门禁，退出码 0 表示与期望一致
python tools/selfcheck_guards.py    # 护栏负面用例，退出码 0 表示全部拦住
python tools/smoke_deps.py          # 依赖现状报告
```

环境：Windows 11 / Python 3.13.14。Stage 0 不需要安装任何第三方依赖。

## 三、相对方案的偏差（如实记录）

1. **新增第 5 个示例包 `blocked`**。理由：方案第 3 节的核心原则之一是"依赖阻断"，而原有四组示例
   无法覆盖，增加一个包即可把这条原则变成可运行的证据。属于**增加而非删减**，不影响其他验收项。
2. **Stage 0 内核用标准库实现**（见 ADR-004）。理由：当前环境缺 geopandas/shapely/pyproj，
   先用零依赖跑通语义；Stage 1 换成权威实现并做一致性对比。这是实现细节上的替代，不是语义放宽。
3. **极简 YAML 解析器自研**（Stage 0），Stage 1 改用 PyYAML 并锁版本。已列入 OPEN_ISSUES。
4. **复验对比（compare）未实现**，Stage 1 的 CLI 补齐。`corrected` 包已就绪，届时可直接用。

## 四、明确未完成（不属于 Stage 0 范围）

- Stage 1：十类规则的权威实现、CLI、单元/集成测试、挑战集落地。
- Stage 2：任何模型调用（目前**一次都没有**）。
- Stage 3：Web 界面、异步任务、地图证据视图、复验界面。
- Stage 4：数据集构建、评测执行、A/B/C 对照、任何指标数字。
- Stage 5：README/视频/发布候选、License、CI。

## 五、给验收方的检查建议

1. 优先看 `selfcheck_guards.py` 的 4 个负面用例是否被如实执行（这是最容易造假的环节）。
2. 再核对 `examples/*/expected/aggregate.json` 与 `examples/README.md` 的缺陷真值表是否自洽
   （期望是人工先写的，不是运行后回填）。
3. 最后看 `work/stage0/blocked/report.md`：依赖阻断是否真的没有给出 PASS。
4. 任何"想到了却没做到"的地方请记为 OPEN_ISSUES 新条目，我会先修再进 Stage 1。
