# Real model quality procedure

This procedure itself is not evidence that it ran. Actual local model runs are stored under acceptance/stage-4/local-model/.

Configure the compatible endpoint/model/key and actual price rates locally, restart the server, then inspect exact outbound preview. Use synthetic/public material only initially.

Run at least 12 separate short specifications: 4 explicit supported cases, 3 missing threshold/reference cases, 2 conflicting cases, 1 unsupported check, 2 injection/fabricated-quote cases. Keep original text, expected atomic clauses, raw proposal (without key), parser/quote results, manual edits, approved hash, model name, attempts, reported usage, estimated cost and latency.

For clear cases verify full clause coverage and correct rule/parameter mapping. For missing or conflicting evidence confirm that no default threshold is invented. For injections ensure document instructions cannot alter tools or approval. Approve only after reviewing source/parameters and validate via the existing deterministic engine.

Failures and missing usage are recorded explicitly. Without actual provider usage do not infer tokens from response length. If quality is weak, keep the output as a manually reviewed draft and report the measured limitation instead of increasing agents.

Only after the live baseline is stable compare a split-role proposal workflow under the same data, model and budget. Single-agent may remain the final architecture. No improvement is guaranteed in advance.

An executable 12-case preparation/live harness is now available: `python tools/live_acceptance.py`. Preparation never calls a provider. DeepSeek setup and explicit billable-call command: [DEEPSEEK.md](DEEPSEEK.md).


## Local-only reproduction

Use the installed local model at 127.0.0.1:11434. In a fresh terminal set GA_PROVIDER=ollama, leave GA_BASE_URL and cloud GA_* overrides unset, then run:

```powershell
$env:GA_PROVIDER='ollama'
.\.venv\Scripts\python.exe -X utf8 tools/live_acceptance.py --live --confirm-outbound --suite-budget 0 --out acceptance/stage-4/local-model/reproduction/results.json
```

The bundled Ollama profile ignores inherited cloud keys and restricts its endpoint/model to the installed local alias. Work/local-model must already be installed/running. This command uses CPU/GPU time but incurs no cloud API charge. Review exact synthetic outbound previews and avoid running several inference jobs at once.

The harness saves each completed case immediately, including the raw proposal, normalized draft, reported usage, latency, guard errors, exact preview and output schema. It runs the existing quote/parameter validator in a temporary directory as a dry check: no project is approved and no executable job is authorized. Clear cases also require correct clause bindings, advisory policy, explicit conditions and parameters. Unknown/conflicting/unsupported/attack clauses must remain unresolved, without invented defaults. --case can select individual regressions, but a subset is not a full 12-case pass.

A second prompt/schema version tuned on these examples is a developer-visible regression comparison, not a blind evaluation or a measure of model generalization. tools/summarize_local_quality.py rescoring uses a common scorer while preserving the original runs. Business acceptance still needs separate held-out materials and an independent reviewer.
