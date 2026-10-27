# Three-minute demonstration script

This script now has an authentic automated synthetic-workflow recording (182.16 seconds), captured by tests/ui/browser-test.cjs --demo. Evidence: acceptance/stage-3/browser/latest.json and its referenced video. A convenient MP4 is delivered alongside the repository as GeoAcceptance-离线流程演示.mp4. The reviewer is explicitly labelled automated, not a real user; this is an offline demonstration, not a live-model video. Attachment saving was cancelled by the headless environment; the recording must not be described as proof of successful native file saving.

00:00–00:25 · Create 含缺陷数据 example. Explain the inputs and immutable snapshot. Show that model configuration is absent and manual baseline is labelled.
00:25–01:10 · Generate the draft; show exact source quotes and parameters. Enter reviewer, explicitly confirm, approve. Explain that approval is not a PASS verdict.
01:10–01:50 · Execute checks. Show a failed field, an outside/invalid point and its source record. Download JSON and HTML. Invalid coordinates remain in the table even if not plotted.
01:50–02:35 · Upload corrected CSV as a new batch. Execute and compare with the first run. Explain duplicate identity, pending deletion, missing evidence and why an all-green view cannot be forced.
02:35–03:00 · Show audit/version trail and the per-case benchmark report. Explicitly disclose that no live model/multi-agent result or user ROI has been measured yet.

Optional live variant: configure a real provider, display outbound preview and mode=live call records. Do not record the key or any customer input.
