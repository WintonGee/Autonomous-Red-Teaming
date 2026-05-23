# Measurements

Scorecards from the measurement harness (`python -m src.measure`). Each run
writes `<timestamp>.json` + `latest.json` and appends one row to `trend.tsv`
(`ts, mode, n_skills, rediscovery_rate, n_findings`), so improvement over time is
a number, not a claim.

These are reproducible run artifacts and are gitignored (the directory is kept via
`.gitkeep`). Regenerate with:

```bash
python -m src.measure            # offline, deterministic (faithful fixture)
python -m src.measure --live     # against the live lab on :3001
```

`rediscovery_rate` = fraction of the ground-truth issues in
`groundtruth/juice-shop.json` that the engagement actually found. Baselines run
with the LLM evaluator OFF for comparability; add `--use-llm` to opt in.
