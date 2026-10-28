# GeoAcceptance

空间数据交付验收工作台：模型提出规则，人审批准，确定性工具执行检查与整改复验。

**0.6.0-rc1 升级候选：双角色协作审查、按来源的时效规则多实例、POI 试点模板。双角色没有在当前开发对照中胜过单次生成，默认仍为 single。**

## 本地运行

本机已有运行环境时，双击 `start-v06.cmd`，打开 http://127.0.0.1:8768/ 。使用独立的 `work/v06-app-v2`；已有项目目录保持保留。Ollama + Qwen3 4B 在本机推理，无云端 API 调用费。

新机器先创建 Python 3.13 虚拟环境并安装 `requirements.lock.txt`，再按 [本地模型说明](docs/LOCAL_MODEL.md) 安装官方运行时和模型。源码包不含虚拟环境、模型权重、密钥或运行数据。已有 `start-local.cmd` / 8766 入口仍保留。

## 本轮功能

- **可选协作审查**：提议者与审查者使用同一本地模型、隔离角色上下文。审查者可自主选择原文、字典或契约查询，最多一轮查询、四次模型调用、一次修订。模型没有审批权限，修订不冒充已复审。
- **同类规则多实例**：先支持 freshness。显式 `仅对 source="municipal"` / `For source="municipal"` 语法由程序解析并绑定范围；模型选择时效参数和证据，不能猜测来源、别名、默认时间或覆盖范围。
- **整改防错**：实例使用稳定 ID；范围进入规则指纹。改变 POI 来源、移出旧规则范围须业务复核，不能自动关闭原问题。未知来源、零匹配实例不判通过。
- **可审核界面**：审查意见、查询记录、修订前后、来源范围及执行数量；JSON/HTML 保留实际规则实例。
- **POI 试点准备**：[试点流程](docs/POI_PILOT.md)与空白标签/计时表已准备，真实业务材料和独立审核尚未到位。

## 真实本地对照：不回避负结果

4 份开发者编写的合成说明，共 40 条要求，三组均进行真实本地调用。不是独立人工金标准，也不是生产准确率。

| 方案 | 完整映射 | 实际调用 | Token |
|---|---:|---:|---:|
| 单次生成 | 38/40 | 4 | 19,102 |
| 同角色自检 | 38/40 | 10 | 75,824 |
| 双角色审查 | 37/40 | 11 | 66,506 |

双角色 Token 约为单次生成的 3.48 倍，未达到预设采用标准，因此仅保留实验选项。模型角色隔离不是统计独立性。审核耗时和客户收益尚未测量。评测途中环境重置记录已保留；已完成样例从断点恢复，未完成调用的 Token 不伪填为零。

原始输出、失败轮次、冻结输入和精确源码快照在 `acceptance/v06/review-ablation-*` 与 `eval/review-dev-v1`；[升级说明](docs/V06_UPGRADE.md)解释测量边界。

## 验证与交付

本地记录：`acceptance/v06/STATUS.json`。跨平台 CI 会执行原有门禁、应用/协作/范围测试、真实浏览器与 Docker HTTP 流程；以实际 Actions 结果为准，不把配置当作通过证据。

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
.venv\Scripts\python.exe tools/stage0_gate.py
.venv\Scripts\python.exe tools/recheck_probes.py --out work/core-probes.json
.venv\Scripts\python.exe tools/compare_probes.py
.venv\Scripts\python.exe tools/verify_release_evidence.py
```

源码扫描和打包：`python tools/release_check.py --zip --version 0.6.0-rc1`。大型历史录像在 GitHub 分段保存，`python tools/restore_recording.py` 校验还原；源码 ZIP 已含原录像，见 [远端制品说明](docs/REMOTE_ARTIFACTS.md)。

## 能力边界

目前是本地单用户原型，无租户身份/权限体系。支持 CSV、显式 EPSG:4326 的二维 Point GeoJSON、单个简单 Polygon；多实例先限 freshness、同一枚举字段的互斥精确值。所有草案逐项人工复核。没有自动业务批准、客户上线、通用准确率、零幻觉、ROI 或多 Agent 优越性的结论。

0.5.x 的 80 条开发评测与历史 CI 单独保留，不能当作这轮的新盲测：[历史发布记录](docs/releases/0.5.0-rc1.md)。

MIT licensed. English: local spatial-delivery assurance with optional bounded proposal/review collaboration. Current developer ablation does not support promoting multi-agent review as the default.
