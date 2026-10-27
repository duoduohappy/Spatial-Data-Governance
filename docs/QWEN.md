# 通义千问接入与 Key 申请

核对日期：2026-10-27。默认：阿里云百炼华北2（北京）、qwen-plus、非思考 JSON 输出。程序接入已实现，实际账号鉴权与模型效果尚未验证。

## 申请步骤

1. 打开 https://bailian.console.aliyun.com/cn-beijing/model/settings/api-key ，注册或登录阿里云账号。按页面要求由本人完成实名认证。
2. 地域选择“华北2（北京）”。若首次使用，按页面提示阅读协议并开通百炼。
3. 进入 API Key 页面，点击“创建 API Key”。个人测试可选自己的阿里云主账号、默认业务空间；若页面允许填写名称，可填 GeoAcceptance。创建后复制密钥，不发聊天、不截图、不放 Git。
4. 在模型广场找到 qwen-plus，确认账号可调用、免费额度及有效期。若账号符合条件且模型详情有“免费额度用完即停”开关，可开启后先做小规模测试。没有免费额度时，是否付费由用户决定；程序不购买套餐或充值。
5. 打开仓库内 work/private/qwen.env，在 DASHSCOPE_API_KEY= 后粘贴完整 Key 并保存，再双击 start-qwen.cmd。不会再要求弹窗或终端输入 Key；环境变量 DASHSCOPE_API_KEY 仍可使用。本机配置文件优先，其他服务留下的 GA_API_KEY 不会混用。
6. 打开 http://127.0.0.1:8765 ，导入示例，在交付概览核对模型 qwen-plus 和外发预览，再请求“真实模型生成”。启动本身不调用模型。

关闭启动器窗口后，该服务随之停止。再次启动时自动读取已保存的 work/private/qwen.env，不再重复输入。该文件是本机明文配置，已被 Git、Docker 上下文及源码 ZIP 排除。若提示端口占用，请先关闭原服务窗口。

## 参数

- GA_PROVIDER=qwen
- GA_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
- GA_MODEL=qwen-plus
- DASHSCOPE_API_KEY：北京地域的百炼 Key
- GA_CURRENCY=CNY；GA_THINKING=disabled

该北京预设固定 qwen-plus 非思考模式，发送 enable_thinking=false 与 response_format=json_object。支持同价快照 qwen-plus-2025-12-01；其他模型、地域或思考模式需另配兼容接口和正确价格，不能沿用本预设。

截至核对日，北京 qwen-plus 在输入不超过 128K Token 时，原价每百万输入 0.8 元、非思考输出 2 元。程序对输入 UTF-8 字节加消息开销设 120,000 上限，按保守字节 Token 预估留在该价格档；更长输入受控拒绝。实际账单受活动、缓存、价格调整和供应商计量影响。费用字段是人民币估算，不是官方账单。单任务预算默认 0.50 元，失败重试保留预留金额。缺用量时成本为未知。启动器重置为该已核对预设；价格变更后须更新预设与测试。

## 验收

```powershell
.\.venv\Scripts\python.exe -X utf8 -m geoacceptance.qwen_launcher --check
$env:GA_PROVIDER='qwen'
.\.venv\Scripts\python.exe -X utf8 tools/live_acceptance.py --out acceptance/stage-4/live-qwen/results.json
```

上述命令不请求模型。检查生成的预览后，在同一终端已配置 DASHSCOPE_API_KEY 的前提下，显式添加 `--live --confirm-outbound --suite-budget 3` 才发起真实请求。自动检查结果仍需人工复核，不会自动批准或宣称全部验收完成。

常见问题：401 优先检查 Key 与地域；403 检查模型/业务空间权限；余额不足检查可用额度。通义千问聊天应用账号的可用性不等于百炼 API 账户已有可用额度。

## 官方依据

- 获取 API Key：https://help.aliyun.com/zh/model-studio/get-api-key
- 开通条件：https://help.aliyun.com/zh/model-studio/faq-about-alibaba-cloud-model-studio
- 接口及地域：https://help.aliyun.com/zh/model-studio/compatibility-of-openai-with-dashscope
- JSON 模式：https://help.aliyun.com/zh/model-studio/qwen-structured-output
- 模型与价格：https://help.aliyun.com/zh/model-studio/model-pricing

## 首次实际调用记录（2026-10-27）

本机已检测到 Qwen Key 配置。首次合成 clean 示例请求失败，旧客户端只记录 ModelError，未保存 HTTP 状态；两次尝试均无供应商用量，费用未知，保留预留金额。证据见 acceptance/stage-4/live-qwen-http/latest.json。已补充安全的 HTTP 状态/错误分类，对 401 等不可重试错误不再重复调用。运行中的用户服务须重启才能加载修复；真实云端联通与模型质量仍未验收。

## 已授权复测：HTTP 403

用户授权单项合成测试、上限人民币 0.50 元。重启后实际仅请求一次，HTTP 403 即停止，预留 0.0217808 元，无用量/实际费用数据。未追加收费请求。403 的具体业务码在该运行版本中未保留，不能据此断定欠费；需核对服务开通、Key 模型权限、业务空间权限和免费额度状态。证据见 acceptance/stage-4/live-qwen-http/20261027T010042Z/。已准备安全业务错误码捕获并在本地测试，不保存原始错误消息或 Key。
