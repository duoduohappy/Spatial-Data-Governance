# Authorized Qwen smoke recheck · 2026-10-27

Authorization: one synthetic generation job, at most two attempts, CNY 0.50 reservation ceiling. Actual: one attempt; HTTP 403; stopped without retry. Reserved CNY 0.0217808. Provider usage/cost unknown, not a statement of an actual debit or zero charge.

Cloud model acceptance: FAIL / NOT ACCEPTED. Exact business error code was not retained by that running version, so account activation, key/model/workspace restrictions and free-tier exhaustion remain hypotheses, not findings. Public unauthenticated models GET returned 401 JSON, consistent with a reachable endpoint; this does not authenticate the user's key.

No additional billable model calls authorized. Safe provider-code capture is prepared and locally tested; the running process will require a later restart before using it. Check console account/model/key scope before any further paid test.

Official reference: https://help.aliyun.com/zh/model-studio/error-code
