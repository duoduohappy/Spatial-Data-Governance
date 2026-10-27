# Quick start (Windows)

Use Python 3.13.14. A new local .venv was created for this candidate, all 22 locked dependencies installed successfully, and the core, compare, schema and application checks reran successfully in that environment. Python 3.11 support is not claimed. Installation evidence: acceptance/stage-5/clean-install.txt; fresh-env-verify.txt; check-summary.json. The delivered local folder is ready to run with start.cmd; the source ZIP requires installation.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -X utf8 -m geoacceptance.server --port 8765
```

Open http://127.0.0.1:8765 in a local browser. Or double-click start.cmd after installation.

1. Click 含缺陷数据 to import a public synthetic example.
2. Generate 离线规则基线. This makes no model call.
3. Open 条款与审核. Check quotes, policy, parameters and missing evidence. Expand JSON to correct a proposal if needed.
4. Enter reviewer, check the confirmation box, approve the current revision.
5. Execute checks and inspect FAIL/INDETERMINATE/PASS, table evidence and invalid coordinates.
6. In 整改复验, upload examples/corrected/poi.csv into the already-approved defective project. This creates a new immutable batch with the same ruler. Execute it.
7. Compare the two completed runs. Duplicate original identifiers may prevent a fully comparable result; do not edit the report to make it green.

## Optional real model

An API key authenticates requests to a model provider; it is not the model itself. You do not need to buy anything to use the offline workbench. Cloud API charges and trial availability depend on your provider. The program does not buy credits or create accounts.

```powershell
$env:GA_BASE_URL = 'https://YOUR-PROVIDER.example/v1'
$env:GA_MODEL = 'YOUR-MODEL'
$env:GA_API_KEY = 'set locally, never put in Git'
$env:GA_INPUT_USD_PER_MILLION = 'your actual input price'
$env:GA_OUTPUT_USD_PER_MILLION = 'your actual output price'
.\.venv\Scripts\python.exe -X utf8 -m geoacceptance.server
```

A verified free/local endpoint can use price 0. A missing price is unknown, not free: live calls are blocked until price configuration is explicit. Provider rates are user-entered and should be kept current. The per-job reservation is a conservative estimate, not an invoice guarantee. All failed attempts retain a reservation.

The process reads environment variables. It does not automatically load .env. Compose does support interpolation from its .env, which must remain untracked. Base URL is the base API path, e.g. ending /v1, not the full /chat/completions URL. HTTPS required except localhost models. Redirects are rejected to protect authorization headers.

Live requests require confirmation of the exact outbound preview in the UI. The key never goes to the browser. The local Ollama/Qwen3 4B path has now passed the documented developer pipeline checks without a key. Cloud Qwen previously returned HTTP 403. See LOCAL_MODEL.md and RELEASE_STATUS.md for exact scope and remaining external gates.

## CLI without browser

```powershell
python -m geoacceptance.appcli example clean
python -m geoacceptance.appcli draft PROJECT_ID --mode manual
python -m geoacceptance.appcli show PROJECT_ID
# Save the draft to a JSON file, review it, and use its CURRENT revision.
python -m geoacceptance.appcli approve PROJECT_ID --proposal draft.json --revision 2 --reviewer YourName
python -m geoacceptance.appcli execute PROJECT_ID
```

The inherited CLI also remains available: `python -m geoacceptance.cli validate --bundle examples/clean --json work/report.json --html work/report.html`. `regress` is only a frozen-example test, not a production validation entry.

## Reproducibility

```powershell
python tools/stage0_gate.py
python tools/recheck_probes.py
python tools/compare_probes.py
python tests/test_application.py
python eval/run_offline.py
python tools/release_check.py
```

For the optional DOM-only UI test: `npm install --prefix tests/ui`, then `node tests/ui/dom-test.cjs`. It does not count as browser visual QA. No Node runtime is needed to run the application.

## Docker

`docker compose up --build` is supplied for an environment with Docker. It has NOT been executed in this environment. Bind is limited to host loopback in compose. Do not change it to a public unauthenticated deployment.
## Optional budget controls

`GA_TIMEOUT_SECONDS` (1–120), `GA_MAX_CALLS` (1–3), `GA_MAX_OUTPUT_TOKENS` (1–16000), `GA_MAX_INPUT_CHARS` (1–100000), and `GA_JOB_BUDGET_USD` configure the job limits. They are process environment variables. Failed attempts retain cost reservations. Actual provider usage can remain unknown and must be reported as such.

This candidate is distributed as source. A separately installable wheel/package and remote hosting have not been validated; use the documented clone/source + requirements workflow.

## DeepSeek shortcut

Use `start-deepseek.cmd` with the private local key file documented in DEEPSEEK.md and the official DeepSeek/CNY preset. Read [DEEPSEEK.md](DEEPSEEK.md) before live calls. Do not put yuan prices in the legacy USD variables.

## Real-browser reproduction

`npm ci --prefix tests/ui`, then `node tests/ui/node_modules/playwright-core/cli.js install chromium --only-shell`. Set `GA_TEST_BROWSER=bundled` to use the downloaded engine and run `node tests/ui/browser-test.cjs`. Add `--demo` to record an approximately three-minute automated synthetic review. It starts an isolated server/data directory, leaves user projects unchanged, and removes provider settings from the child environment. Screenshots, video, test results and any download limitation are saved under acceptance/stage-3/browser. A cancelled browser save is explicitly recorded separately from successful HTTP export verification.

## Qwen cloud shortcut

Use `start-qwen.cmd` or `python -m geoacceptance.qwen_launcher`. This is the Beijing qwen-plus preset reading DASHSCOPE_API_KEY from work/private/qwen.env without a prompt. See [QWEN.md](QWEN.md). A prior authorized cloud test returned HTTP 403; local mode below does not require a key.

## Local model (current selection)

Use `start-local.cmd` and port 8766 for the installed local-only Qwen3 4B runtime. This uses a separate work/local-app data directory, requires no key, and strips cloud credentials. See [LOCAL_MODEL.md](LOCAL_MODEL.md) for portable installation and real inference evidence.
