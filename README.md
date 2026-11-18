# SupeRR Selector — Season 2

An evidence-led cricket analytics project for pressure performance in T20 cricket.
The project separates a player's Performance Score from the reliability of the evidence
supporting it, and carries uncertainty and eligibility shortfalls into its outputs.

## Phase 6 status

The dashboard, presentation, and PDF are built locally from frozen Phase 5 outputs.
The current communication gate is **PASS_WITH_NOTES**, pending owner review. The public
repository intentionally contains source and reproducibility instructions only. It does
not contain the source data, player ranking files, or generated player-facing deliverables.

## Project structure

- `src/pressure/` — pressure definitions and validation.
- `src/performance/` — Phase 3 performance components.
- `src/reliability/` — Phase 4 shrinkage, reliability, and format analysis.
- `src/ranking/` — Phase 5 ranking and sensitivity methods.
- `src/deliverables/` — Phase 6 dashboard, deck, report, and verification builders.
- `tests/` — phase-specific regression and acceptance tests.
- `config/methodology.yaml` — approved analysis settings.
- `docs/DATA_DICTIONARY.md` — definitions of ranking and dashboard fields.

## Local setup

Use Python 3.12 and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Place the licensed cricket data pack and the project's local Phase 0–5 outputs in the
expected paths described in the phase reports. These files are excluded from GitHub;
redistribution rights have not been established. Do not commit them.

## Reproduce Phase 6

With the local Phase 5 artifacts in place:

```bash
python -m pytest -q tests/test_phase6_deliverables.py
python -m src.deliverables.run_phase6
```

The driver rebuilds the offline dashboard, presentation, and PDF; runs browser, layout,
content, and frozen-input checks; and writes detailed evidence under
`reports/phase_6/logs/`. It does not rerun the ranking or model pipeline.

## Frozen result boundaries

Final player-level findings and all generated deliverables remain local pending owner
review. The public repository contains no ranking rows, individual scores, or player
lists. See the local Phase 6 report for the complete uncertainty and limitation record.
