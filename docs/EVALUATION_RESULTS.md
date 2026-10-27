# Evaluation results and limits

Read `eval/results/offline-evaluation.json` for per-case inputs, split, expected result, actual result, time and limitations.

Executed offline profile:
- 80 clause cases: 37 development / 17 validation / 26 nominal test. Manual deterministic mapping matched the expected type for all 80 in this author-visible template set. Repeated templates and hand-written matching make this a regression/reference measure, not evidence of general natural-language ability.
- 50 synthetic data batches: 20 development / 10 validation / 20 nominal test, with 100/1,000/10,000 records. Profile is R01–R09; R10 candidate matching is excluded from throughput. Test batch outcomes matched 20/20; no false accepts among the 16 nonpassing test batches. This finite synthetic test does not establish real-world zero risk.
- Real public USGS snapshot: 35 point events, mapped explicitly from event id/place/time/lon/lat into the canonical schema; 2D mapping omits depth. Existing explicit profile passed this snapshot with no findings. No known real defect is claimed. It demonstrates public data IO and reproducibility, not spatial truth or positional accuracy.

`python eval/run_offline.py` regenerates the synthetic batches and evaluation. The frozen USGS input is read locally. `tools/fetch_public_sample.py` can explicitly fetch a NEW snapshot, whose SHA and results may differ; do not silently replace the frozen snapshot in a benchmark claim.

No real provider was configured: live single-agent metrics = NOT_RUN; multi-agent metrics = NOT_RUN. Human review time savings = NOT_MEASURED. Mock transport calls in tests only verify code behavior. Do not relabel the deterministic baseline as AI or count its zero model calls as measured AI cost reduction.

The source author could see test generation templates; these are not a sealed independent holdout. Before making generality or ROI claims, acquire unseen customer-like documents, separate annotations from implementation, use independent reviewers and time the full correction/review/report workflow. Record cost, total tasks, failures, coverage and all changed conditions. Keep false accepts separate from unknowns and false rejects.
