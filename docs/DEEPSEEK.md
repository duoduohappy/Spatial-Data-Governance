# DeepSeek integration (verified against official docs 2026-10-27)

The adapter is implemented. Real authentication and model quality are NOT verified until a real key is supplied locally.

## Start

Close the previous terminal running port 8765. Double-click start-deepseek.cmd, or run `.\.venv\Scripts\python.exe -X utf8 -m geoacceptance.deepseek_launcher`. The CMD launcher calls Python directly and does not require changing PowerShell execution policy. Enter the API key in its hidden prompt. The key is retained only in the launcher/server environment and never written to the source or browser. Existing GA_API_KEY or DEEPSEEK_API_KEY is also supported. Do not paste a key into chat.

Official key console: https://platform.deepseek.com/api_keys . The user creates the account/key and manages any credit; the application never purchases credits. Chat-app subscription and API access are separate products.

Default preset: `GA_PROVIDER=deepseek`, official base `https://api.deepseek.com`, model `deepseek-flash`, `GA_THINKING=disabled`, max output 8192, timeout 90 seconds, at most 2 calls per job. The official endpoint supports JSON output. Thinking is disabled explicitly to establish a bounded extraction baseline; this is not a claim that it maximizes quality. The model never receives POI rows or coordinates. Review the outbound document/dictionary/header/schema preview before submitting.

## Prices and budgets

The preset uses **CNY**, a conservative high-traffic cache-miss input rate of 2 yuan/million and output rate of 8 yuan/million, checked 2026-10-27. Cache hits and off-peak billing may be lower. Reported cost is an estimate at configured rates, not an invoice or an exchange-rate conversion. No token usage means unknown cost. Change GA_INPUT_PRICE_PER_MILLION / GA_OUTPUT_PRICE_PER_MILLION when rates change. GA_JOB_BUDGET defaults to CNY 0.50 per job; failed retries retain reservations. Legacy *_USD_* prices must not be mixed with a CNY profile.

The DeepSeek preset rejects custom hosts before any request, so its key cannot accidentally be sent to a proxy. Use the separate compatible profile for deliberately configured alternative endpoints.

## Twelve-case live check

Preparation makes no requests:

```powershell
.\.venv\Scripts\python.exe -X utf8 tools/live_acceptance.py
```

Review `acceptance/stage-4/live/*-preview.json`. They contain only the synthetic example specifications and dictionary/schema, not POI records. With the provider/key environment configured locally, run:

```powershell
$env:GA_PROVIDER='deepseek'
# DEEPSEEK_API_KEY must already be configured in this terminal; do not embed it in a script.
.\.venv\Scripts\python.exe -X utf8 tools/live_acceptance.py --live --confirm-outbound --suite-budget 3
```

The suite limit is CNY 3 for this profile. It caps conservative reservations across attempts and cases. Four explicit cases, three missing-evidence cases, two conflicting cases, one unsupported case and two attack cases produce per-case raw drafts, automated checks, usage/cost estimates, latency and outstanding human-review status. A successful automated check is still REVIEW_PENDING, never automatic release approval. Provider/network failure is not counted as an injection guard success. The cases are developer-visible, not an independent blind benchmark.

Official references:
- API/model names: https://api-docs.deepseek.com/zh-cn/
- Current rates: https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
- JSON mode: https://api-docs.deepseek.com/zh-cn/guides/json_mode/
- Thinking switch: https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/

Updated local entry method: the Python/CMD launcher now reads `work/private/deepseek.env` (`DEEPSEEK_API_KEY=...`) and does not prompt. This runtime file is excluded from Git/Docker/source ZIP; it is a local plaintext credential file. The user-requested Qwen equivalent is `work/private/qwen.env`.
