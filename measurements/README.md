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

## What this number does and does not mean

Rediscovery measures *known* issues found — it is only as honest as the
ground-truth file. To stop it from "reading its own answer key," ground truth
deliberately includes **coverage gaps**: issues whose `detected_by` skill does
not exist yet (e.g. `js-robots-disclosure`). They hold the rate below 100% and
name the next skill to build — so a rising rate reflects real new capability, not
a fixed checklist scoring itself. It says nothing about *unknown* vulnerabilities;
that is what the LLM Evaluator + distillation loop is for.
