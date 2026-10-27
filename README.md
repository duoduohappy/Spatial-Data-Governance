# GeoAcceptance · 空间数据交付验收助手

**0.5.0-rc1 · 本地功能验收通过的发布候选版**

交付说明 → 模型提议／离线规则基线 → 人工审核 → 确定性空间检查 → 证据报告 → 整改复验。

用于回答：这批空间数据满足哪些已确认要求、哪里失败、哪些依据尚不足？模型没有批准权，不直接决定 PASS。项目不替代正式测绘、合同验收或数据真实性证明。

## 开始使用

本机已安装本地 Ollama + Qwen3 4B。双击 `start-local.cmd`，打开 **http://127.0.0.1:8766/**。无需 API Key，不产生云端 API 调用费，仍消耗本机硬件与电力。本地数据在 `work/local-app`，模型与程序在 `work/local-model`；这些目录不随 Git、Docker 上下文或源码 ZIP 分发。

换机器需要 Python 3.13 环境（已实测 3.13.14；不声称支持 3.11），先安装锁定依赖：

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -X utf8 tools/setup_local_model.py
.\.venv\Scripts\python.exe -X utf8 -m geoacceptance.local_launcher
```

安装模型需要联网下载数 GB 官方文件。也可双击 `start.cmd` 体验不调用模型的确定性基线，默认端口 8765。

1. 创建含缺陷示例或导入交付包。
2. 生成草案；真实模型只接收经展示确认的交付说明、字典、表头及规则结构，不发送 POI 记录值。
3. 逐项核对原文、字段、条件、参数与待澄清项，填写审核人并批准当前版本。
4. 执行检查，查看地图／表格和来源证据，导出 JSON、HTML。
5. 上传整改批次，沿同一批准规则复验。原始 ID 重复或规则变化会阻止台账假关闭；批次 PASS 不等于全部台账可比较。

[快速开始](docs/QUICKSTART.md) · [本地模型说明](docs/LOCAL_MODEL.md) · [架构](docs/CONTINUATION_ARCHITECTURE.md)

## 已完成的本地检查

| 检查 | 实测结果 | 边界 |
|---|---|---|
| 确定性内核 | 六包、30 项核心探针、33 项 compare／参数探针通过 | 原始验收历史保留，新重跑是实现方自检 |
| 应用与 HTTP | 33 项测试通过；端到端 HTTP 工作流通过 | 合成数据；含正向关闭与重复 ID 无法关闭反例 |
| 本地真实模型管线 | 第 4 轮 12/12 自动检查通过 | 包含证据编译器隔离无依据规则，不等于原始模型零错误 |
| 新表述开发检查 | 8 份说明、80 条原子要求；编译后完整映射 75/80，原始语义映射 74/80，覆盖 80/80 | 开发者标注、事先冻结，不是独立人工金标准；5 条仍需复核／修订 |
| 工作台真实链路 | 新生成草案零参数修改，经 Codex 开发复核后 clean／defective／corrected 为 PASS／FAIL／PASS | 复核者是实现者，不能冒充用户或外部验收 |
| 浏览器 | 12 项 Chromium 桌面／手机检查；内置浏览器实际保存 JSON 与 HTML，字节与接口一致 | 独立沙箱 Chromium 保存仍报权限不足，未掩盖该差异 |
| 演示 | 182.16 秒真实自动化操作录像 | 合成数据、自动化审核，不是客户案例或效率实验 |

完整证据：[阶段状态](docs/RELEASE_STATUS.md)、[模型质量记录](docs/LOCAL_MODEL_QUALITY.md)、[`acceptance/stage-5/STATUS.json`](acceptance/stage-5/STATUS.json)。原有失败轮次、中断记录、原始模型输出和隔离原因均保留。

## 为什么加入证据编译器

模型负责选择条款、参数、语义条件和证据位置。程序从模型的规则参数复制值，生成规范单位与字面量，再核对其是否出现在原文中；不让模型重复抄同一个值，也不替模型改成“正确答案”。缺日期、缺阈值、引用不成立或条款尚未解决时，相关规则被隔离，对应要求保留待澄清。

当前支持 R01–R10 十类规则，一类一个实例；规范 CSV 列或显式 EPSG:4326 的二维 Point GeoJSON；单个简单项目多边形。任意字段映射、多部件／带孔区域、一般 CRS 转换不在首版适配器范围。候选分句也有识别边界，不能省去人工审核。

本机可信用户工作台，没有登录或多租户隔离，不能直接暴露公网。重复候选 O(n²) 路径没有被拿来宣称万条可扩展吞吐。

## 尚未完成的外部验收

Docker 配置及实际工作流 CI 已准备，但本机没有 Docker 引擎；目标 GitHub 仓库已提供，正在上传并等待 Actions 实际结果。独立人工标注、真实业务审核时间与收益也尚未测量。没有多 Agent 优越性、通用准确率、零幻觉或生产认证的结论。**本地功能通过不等于 Stage 2–5 全部独立验收通过。**

离线基线、50 批合成注入与 USGS 公开点案例的历史结果见 [评测说明](docs/EVALUATION_RESULTS.md)，与模型成绩分开报告。

## 其他模型与复现

- [DeepSeek 配置](docs/DEEPSEEK.md)：通过本机私有配置文件填写 Key，无输入弹窗；未经授权不发生云调用。
- [千问云端配置](docs/QWEN.md)：已授权测试曾返回 HTTP 403；本地模型路径不依赖该服务。
- [真实模型质量流程](docs/LIVE_ACCEPTANCE.md)：包括调用用量、原始输出、输出契约、版本摘要和未通过记录。
- [API](docs/API.md) · [许可及第三方来源](THIRD_PARTY.md) · [演示脚本](docs/DEMO.md)

English: A local spatial-delivery assurance workbench. Models propose; people review; deterministic tools decide. Local functional checks pass, while Docker/remote CI and independent business validation remain pending. Developer-visible results are not blind accuracy, measured ROI or multi-agent superiority.

MIT licensed. Models, dependencies and public data retain their own terms. Target repository: duoduohappy/Spatial-Data-Governance; remote acceptance is in progress.
