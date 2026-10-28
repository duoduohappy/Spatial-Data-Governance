# Reproducing this developer experiment

experiment-source.zip preserves the exact source. source-hashes.json records original-byte and LF-normalized hashes. Extract into work/repro-v2, create work/repro-v2/work, then invoke that snapshot's tools/review_ablation.py with the saved dataset and a new output directory. The installed local Ollama model must be running. No cloud provider is used.

V2 uses an exposed developer set after a structural review-contract fix, not independent holdout. Archived source predates subsequent scope/report refinements. Unfinished interrupted inference has no claimed token usage. Cold loading and interruption prevent treating elapsed time as stable latency or human-efficiency evidence. Hardware/runtime nondeterminism may change new outputs.
