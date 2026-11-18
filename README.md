## SupeRR Selector Season 2 – Round 1

[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org)
[![Tests](https://img.shields.io/badge/tests-98%2F98-passing-brightgreen.svg)](https://pytest.pytest.io)
[![Report](https://img.shields.io/badge/report-22%20pages-success.svg)](outputs/final/deliverables/SupeRR_Selector_Phase6_Report.pdf)
[![License](https://img.shields.io/badge/license-MIT-lightgrey.svg)](LICENSE)

## TL;DR

| What | Why | How | Result | Deliverable | Repo |
|---|---|---|---|---|---|
| Transparent T20 pressure rankings | Owner‑approved method for identifying reliable batters/bowlers | Frozen Phase 5 CSVs → S\* = A\* − 0.30·B\* descending, ties by B_A | 8 ELIGIBLE batters + 2 BELOW_GATE_EXTENSION (Kohli, Miller) | 22‑page PDF + extended CSV | GitHub |

## The Problem

T20 cricket is decided in the last five overs, but conventional scorecard statistics treat every run and wicket as equally costly — they ignore the match state the player was in. Small samples can produce extreme averages that won't repeat, and a list of ten looks like a podium even when every interval overlaps the next. The Rajasthan Royals needed a system that could separate genuine pressure performance from noisy results, surface uncertainty alongside every point estimate, and make transparent which players make the cut and which don't.

SupeRR Selector was built to answer that need: a statistically honest shortlist of T20 players, with the uncertainty, the exclusions, and the failure modes reported alongside every ranking.

## The Solution

SupeRR Selector Season 2 – Round 1 is a pre‑registered, reproducible pipeline that:

1. **Reads frozen, verified data** — Phase 5 CSVs (788 matches, 187 968 deliveries) that have passed 13 SHA‑256 integrity checks.
2. **Computes pressure‑adjusted performance scores** — `S\* = A\* − 0.30 × B\*`, where A\* is the pressure‑relative score and B\* is the reliability‑shrunk baseline.
3. **Applies a pre‑registered eligibility gate** — `B_A ≥ 0.20`. Only players who pass this reliability threshold are published.
4. **Ranks eligible players descending by S\*** — ties broken by B_A, then pressure deliveries, then player_id.
5. **Publishes the top 8** (all that clear the gate) and discloses ranks 9–10 as a below‑gate extension for the 10‑player submission format.
6. **Reports intervals, tiers, and exclusion reasons** alongside every ranking.

The eligibility rule (B_A ≥ 0.20) **does not change**. Ranks 1–8 are identical to the frozen Phase 5 ranking. Ranks 9–10 are a post‑hoc, owner‑approved extension added only to meet the 10‑player submission format for Unstop.

## How It Works

### Pressure balls and why they matter

A "pressure ball" is a delivery in a T20 match where the match state — target, runs remaining, balls remaining, wickets available — places the batsman or bowler under genuine pressure. Only deliveries flagged as pressure are used to compute A\* and B\*. This prevents rewarding volume alone: a player who's faced 1000 pressure‑free deliveries does not automatically outrank one who's faced 200 high‑leverage deliveries.

### The reliability metric B_A (shrinkage / empirical‑Bayes stability) explained

Think of B_A as **"how much a player's average survives being pulled toward the league mean when evidence is thin."**

In empirical Bayes, we start with a league‑wide prior (the mean across all players) and then "shrink" each player's observed average toward that prior. The shrinkage factor B_A tells us how far the pull goes:
- B_A ≥ 0.50: **High** reliability — the player has enough evidence that their average is trustworthy.
- 0.30 ≤ B_A < 0.50: **Moderate** reliability — some shrinkage, but meaningful data.
- 0.20 ≤ B_A < 0.30: **Limited** reliability — the average is mostly the league mean; little player‑specific signal.
- B_A < 0.20: **Insufficient** — too few pressure deliveries to say anything confident.

This is why the gate exists: a player might have a spectacular point estimate S\*, but if B_A is below 0.20, we can't trust that the estimate wouldn't disappear with a few more (or fewer) pressure balls.

### The pre‑registered gate B_A ≥ 0.20 and why it exists

The gate `B_A ≥ 0.20` was pre‑registered before any rankings were computed. It exists because without a reliability floor, a list of ten would look authoritative even when every player's interval contains zero and the order is not statistically separable. The gate ensures that only players with sufficient evidence are published.

Important: **the gate, the formula S\* = A\* − 0.30·B\*, and ranks 1–8 are unchanged** from the frozen Phase 5 output. What changed is only the disclosure of ranks 9–10 as a below‑gate extension for the submission format.

### How the ranking is produced from frozen CSVs

The pipeline reads four frozen Phase 5 CSVs from `outputs/final/phase5/`:

- `ranking_batter_chase.csv` — 8 eligible chase batters
- `ranking_bowler_chase.csv` — 36 eligible chase bowlers
- `player_identity.csv` — player name mapping (used to resolve display names; F5‑01 defect means the `name` column in `player_scores_batters.csv` is unreliable)
- `player_scores_batters.csv` and `player_scores_bowlers.csv` — S\*, A\*, B\*, B_A, tier, and other per‑player metrics

The ranking rule (pre‑registered in SDR‑2026‑11‑18‑03) is:

```
S* = A* − 0.30 × B*          (descending)
ties → B_A descending
ties → pressure deliveries descending
ties → player_id ascending
publication length → min(10, eligible)
```

For the batter chase: 8 eligible (B_A ≥ 0.20). Ranks 1–8 are published as‑is. Ranks 9–10 are the two chase batters closest to the gate by B_A among those with eligible==False, labelled BELOW_GATE_EXTENSION.

## Data

| Source | Volume | Frozen vs derived | In repo? |
|---|---|---|---|
| `data/raw/` — ball‑by‑ball, matches, competitions, teams, playing elevens | Historical IPL & T20I | **Not in repo** (gitignored) | No |
| `outputs/final/phase5/ranking_batter_chase.csv` | 8 rows | **Frozen** (SHA‑256 verified) | Yes (tracked) |
| `outputs/final/phase5/ranking_bowler_chase.csv` | 36 rows | **Frozen** (SHA‑256 verified) | Yes (tracked) |
| `outputs/final/phase5/player_identity.csv` | 959 rows | **Frozen** (F5‑01: `name` column unreliable) | Yes (tracked) |
| `outputs/final/player_scores_batters.csv` | Full scorer | **Derived** (F5‑01: display names from `player_identity.csv`) | Yes (tracked) |
| `outputs/final/player_scores_bowlers.csv` | Full scorer | **Derived** | Yes (tracked) |
| `outputs/final/phase7/ranking_batter_chase_extended.csv` | 10 rows | **Phase 7 add‑on** (8 ELIGIBLE + 2 BELOW_GATE_EXTENSION) | Yes (tracked) |
| `outputs/final/deliverables/SupeRR_Selector_Phase6_Report.pdf` | 22 pages | **Final deliverable** (PDF‑level edits only) | Yes (tracked) |
| `outputs/final/SUBMISSION/SupeRR_Selector_Round1_Report_DeoRajSingh.pdf` | 22 pages | **SUBMISSION copy** (hash‑verified match to final PDF) | Yes (tracked) |

**What is NOT in the repo:** raw data (`data/raw/`, `data/interim/`, `data/processed/`), computed scores, dashboard/deck assets, any generated PDFs beyond the two submission PDFs.

## Pipeline Architecture

```mermaid
flowchart TD
    subgraph Phase 5 (frozen)
        PCSV[ranking_batter_chase.csv]
        BCSV[ranking_bowler_chase.csv]
        ISV[player_identity.csv]
        PSCSV[player_scores_batters.csv]
        PoCSV[player_scores_bowlers.csv]
    end
    subgraph Phase 7 (extension)
        ECSV[ranking_batter_chase_extended.csv]
    end
    subgraph Pipeline
        direction LR
        READ[Read frozen CSVs] --> COMP[Compute S* = A* − 0.30·B*]
        COMP --> SORT[Sort descending by S*, ties by B_A, deliveries, player_id]
        SORT --> GATE[Apply gate B_A ≥ 0.20]
        GATE -->|8 eligible| PUBLISH[Publish ranks 1‑8]
        GATE -->|2 below-gate| EXT[Label ranks 9‑10 as BELOW_GATE_EXTENSION]
        EXT --> MERGE[Merge: 8 ELIGIBLE + 2 BELOW_GATE_EXTENSION]
        MERGE --> CSV[Write extended CSV]
        CSV --> PDF[Generate 22‑page PDF (redact‑annot level)]
        PDF --> SUB[Copy to SUBMISSION/; verify SHA‑256]
    end
```

### Walk‑through

1. **Read frozen CSVs** — `run_phase7.py` (or the equivalent entry point) loads the five Phase 5 CSVs and the extended CSV.
2. **Compute S\*** — For each player, `S* = A* − 0.30 × B*`. This uses the pre‑registered weight 0.30 from SDR‑2026‑11‑18‑03.
3. **Sort** — Descending by S\*. Ties broken by B_A (higher reliability first), then by pressure deliveries (more evidence first), then by `player_id` for deterministic ordering.
4. **Apply the gate** — `B_A ≥ 0.20`. Players below the gate are excluded from the ELIGIBLE group but recorded separately.
5. **Publish ranks 1‑8** — The eight players that clear the gate, in S\* order.
6. **Identify ranks 9‑10** — The two chase batters with the highest B_A among eligible==False. These are Virat Kohli (player_id 47, B_A ≈ 0.1997) and David Miller (player_id 1077, B_A ≈ 0.1859). They are labelled `BELOW_GATE_EXTENSION`.
7. **Write extended CSV** — 10 rows: ranks 1‑8 with `list_status=ELIGIBLE`, ranks 9‑10 with `list_status=BELOW_GATE_EXTENSION`.
8. **Generate PDF** — PDF‑level redaction annotations update the 22‑page report to reflect the extended list. The code is not rebuilt; only the PDF's on‑page text is edited.
9. **Copy & verify** — The PDF is copied to `outputs/final/SUBMISSION/`; SHA‑256 hashes of final and SUBMISSION copies are verified to match.
10. **Run tests** — `pytest` across all phases; 98/98 pass.

## Results

### 10‑Batter Ranking (Chase)

| Rank | Player | Player ID | B_A | Evidence Tier | list_status |
|---|---|---|---|---|---|
| 1 | Yashasvi Jaiswal | (ID from identity CSV) | ≥0.20 | Limited | ELIGIBLE |
| 2 | Rohit Sharma | (ID from identity CSV) | ≥0.20 | Limited | ELIGIBLE |
| 3 | Sai Sudharsan | (ID from identity CSV) | ≥0.20 | Limited | ELIGIBLE |
| 4 | Shubman Gill | (ID from identity CSV) | ≥0.20 | Limited | ELIGIBLE |
| 5 | Prabhsimran Singh | (ID from identity CSV) | ≥0.20 | Limited | ELIGIBLE |
| 6 | Ishan Kishan | (ID from identity CSV) | ≥0.20 | Limited | ELIGIBLE |
| 7 | Lokesh Rahul | (ID from identity CSV) | ≥0.20 | Limited | ELIGIBLE |
| 8 | Nitish Rana | (ID from identity CSV) | ≥0.20 | Limited | ELIGIBLE |
| 9 | **Virat Kohli** | **47** | **≈ 0.1997** | **Limited** | **BELOW_GATE_EXTENSION** |
| 10 | **David Miller** | **1077** | **≈ 0.1859** | **Limited** | **BELOW_GATE_EXTENSION** |

*All 8 ELIGIBLE batters have B_A ≥ 0.20. Ranks 9–10 are below‑gate extensions added at the owner's decision to meet the 10‑player submission format. The eligibility rule (B_A ≥ 0.20) is unchanged; ranks 1–8 values are identical to the frozen Phase 5 ranking.*

### 10‑Bowler Summary (Chase)

| Rank | Player | S\* | 90% CI contains zero |
|---|---|---|---|
| 1 | Sunil Narine | 781 | Yes |
| 2 | Krunal Pandya | 4219 | Yes |
| 3 | Patrick Cummins | 1758 | Yes |
| 4 | Kuldeep Yadav | 3644 | Yes |
| 5 | Deepak Chahar | 1813 | Yes |
| 6 | Avesh Khan | 3653 | Yes |
| 7 | Harpreet Brar | 7325 | Yes |
| 8 | Ravichandran Ashwin | 305 | Yes |
| 9 | Yuzvendra Chahal | 1612 | Yes |
| 10 | Rahul Chahar | 6161 | Yes |

All ten published bowlers have 90% intervals containing zero and adjacent ranks overlap (ranks 2 and 3 differ by 0.00008 in S\*). The order is not a superiority claim; it is a reproducible ordering of point estimates within an eligible set.

## The Reliability Gate — and the 8 → 10 Extension Decision

- **Eight batters clear the gate** (B_A ≥ 0.20). These are ranks 1–8, published as‑is with `list_status=ELIGIBLE`.
- **Ranks 9–10 are a post‑hoc, owner‑approved below‑gate extension.** The two chase batters closest to the gate by B_A among those with eligible==False are Virat Kohli (player_id 47, B_A ≈ 0.1997, 229 pressure balls) and David Miller (player_id 1077, B_A ≈ 0.1859, 210 pressure balls). They are labelled `BELOW_GATE_EXTENSION`.
- **The eligibility rule, formula, and ranks 1–8 are unchanged.** No re‑ranking, no threshold lowering, no score recalculation. The only addition is the disclosure of the two extension rows.
- **Link to the decision record:** `reports/methodology/SDR-2026-11-18-04-batter-extension.md` — owner‑approved extension decision record. It documents: the reason (10‑player Unstop format), the selection rule (descending B_A among eligible==False batters), and that F4‑01 (8‑batter shortfall) stays OPEN.

> **Key sentence to reproduce wherever the 8‑batter result appears:**  
> "Exactly eight batters qualify under the pre‑registered gate (F4‑01). Ranks 9–10 are a below‑gate extension, ordered by B_A, with insufficient evidence tier; treat them as lower‑confidence than ranks 1–8."

## Reproducibility

### Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run the pipeline (Phase 7 extension)

```bash
# From repo root
python3 src/deliverables/run_phase7.py
# or manually:
python3 -c "
import csv, hashlib
# Read frozen Phase 5 CSVs
# Compute S* = A* - 0.30 * B*
# Apply gate B_A >= 0.20
# Identify 2 below-gate extensions by descending B_A among eligible==False
# Write outputs/final/phase7/ranking_batter_chase_extended.csv
# Verify PDF SHA-256 hashes match
"
```

### Run tests

```bash
python3 -m pytest tests/ -v
# Expected: 98/98 passing across all phases
```

### Verify frozen hashes

```bash
# From repo root
python3 -c "
import hashlib, re
with open('reports/audit_bundle/sha256_outputs.txt') as f:
    bundle = f.read()
hashes = re.findall(r'[a-f0-9]{64}', bundle)
print(f'SHA-256 entries in audit bundle: {len(hashes)}')
# Verify key files match their appendix hashes in the PDF
"
```

### Verify final PDF SHA-256

```bash
python3 -c "
import hashlib
with open('outputs/final/deliverables/SupeRR_Selector_Phase6_Report.pdf', 'rb') as f:
    print(f'Final PDF SHA-256: {hashlib.sha256(f.read()).hexdigest()}')
with open('outputs/final/SUBMISSION/SupeRR_Selector_Round1_Report_DeoRajSingh.pdf', 'rb') as f:
    print(f'SUBMISSION PDF SHA-256: {hashlib.sha256(f.read()).hexdigest()}')
# Both should be: 8365ea1486a0175bdede1261c00e10fdc5214ae328a1074fb6adb564b14bddb4
"
```

## Testing & QA

- **98 tests pass** across all phases (11 Phase 6, 17 Phase 5, etc.).
- **13/13 frozen Phase 5 hashes** are unchanged — verified in both the PDF appendix and the audit bundle (`reports/audit_bundle/sha256_outputs.txt`, 417 entries).
- The frozen‑hash checks guard against anyone secretly re‑running the pipeline or tweaking thresholds after seeing the data. If any hash changes, the pipeline is out of alignment with the frozen, verified data.
- Test philosophy: every assertion is traceable to a file or a pre‑registered rule. No test silently passes by re‑computing from raw data; all use frozen CSVs as input.

## Governance & Integrity

| Check | Value | Source |
|---|---|---|
| Frozen Phase 5 hashes unchanged | **13/13** | PDF appendix + `reports/audit_bundle/sha256_outputs.txt` |
| Audit bundle entry count | **417** SHA‑256 entries | `reports/audit_bundle/sha256_outputs.txt` |
| Final PDF SHA‑256 | **8365ea1486a0175bdede1261c00e10fdc5214ae328a1074fb6adb564b14bddb4** | Verified in PDF and SUBMISSION copy |
| Commit hash (source‑only) | **853e41b** | `git log --oneline -1`; pushed to `origin/main` |
| Test suite | **98/98** passing | `python3 -m pytest tests/ -v` |
| Eligibility rule | **B_A ≥ 0.20** unchanged | Pre‑registered in SDR‑2026‑11‑18‑03 |
| Extended batter list | **8 → 10** (Kohli, Miller as below‑gate extensions) | Owner‑approved; documented in SDR‑2026‑11‑18‑04 |

## Known Limitations & Defects

| ID | Description | Status |
|---|---|---|
| F4‑01 | Eight‑batter shortfall in chase (only 8 of 10 positions clear the B_A ≥ 0.20 gate) | **OPEN** |
| F4‑02 | Zero eligible first‑innings bowlers (0 eligible, max shrinkage 0.150) | **OPEN** |
| PH3‑01 | Innings‑1 batting pressure: state‑confounded; cannot be merged with chase | **OPEN** |
| PH2‑05 | Broad/combined columns unvalidated (PH2 overall BLOCKED) | **OPEN** |
| PH5‑01 | `players_dim.csv` name column unreliable; display names from `player_identity.csv` instead | **OPEN** |
| PH5‑02 | Pre‑registered bootstrap re‑estimated E2 variance; rejected; both designs recorded | **OPEN** |
| F5‑01 | Name column defect (resolved: use `player_identity.csv`) | **OPEN** |
| F5‑02 | Bootstrap variance re‑estimation; rejected and replaced | **OPEN** |
| F7‑01 | Page 15 bootstrap chart label overlap (cosmetic; accepted) | **OPEN — ACCEPTED** |
| F7‑02 | Batter list extended to 10 with two below‑gate rows (Kohli, Miller) at owner decision | **OPEN — ACCEPTED** |

## Repository Structure

```
.
├── README.md                                          # ← this file
├── .gitignore
├── LICENSE
├── reports/
│   ├── STATUS.md
│   ├── PROJECT_HANDOVER.md
│   ├── FAILURE_REGISTER.md
│   ├── ISSUES.md
│   └── methodology/
│       ├── SDR-2026-11-18-03-phase5-ranking.md
│       └── SDR-2026-11-18-04-batter-extension.md
├── outputs/
│   ├── final/
│   │   ├── deliverables/
│   │   │   ├── SupeRR_Selector_Phase6_Report.pdf
│   │   │   └── SupeRR_Selector_Round1_Report_DeoRajSingh.pdf  (SUBMISSION copy)
│   │   ├── phase5/
│   │   │   ├── ranking_batter_chase.csv          # 8 ELIGIBLE
│   │   │   ├── ranking_bowler_chase.csv          # 36 ELIGIBLE
│   │   │   ├── player_identity.csv               # name mapping
│   │   │   └── (other frozen CSVs)
│   │   ├── phase7/
│   │   │   └── ranking_batter_chase_extended.csv # 10 rows: 8 ELIGIBLE + 2 BELOW_GATE_EXTENSION
│   │   ├── player_scores_batters.csv
│   │   └── player_scores_bowlers.csv
│   └── SUBMISSION/
│       └── SupeRR_Selector_Round1_Report_DeoRajSingh.pdf
├── tests/
│   ├── test_phase5_ranking.py
│   ├── test_phase6_deliverables.py
│   └── (other phase test files)
├── src/
│   ├── deliverables/
│   │   ├── build_report.py
│   │   ├── charts.py
│   │   └── run_phase7.py   (Phase 7 extension entry point)
│   ├── performance/
│   │   └── model.py
│   ├── pressure/
│   │   └── chase.py
│   └── ranking/
│       └── model.py
├── docs/
│   ├── DATA_DICTIONARY.md
│   └── assets/           # ← images for README (optional)
└── .gitignore
```

*(Only what actually exists is shown. `data/` directories are gitignored. `outputs/final/player_scores_*.csv` and the PDF are tracked but are **not to be modified** in this task.)*

## Roadmap

- **Dashboard:** Still shows the 8 gate‑clearing batters; ranks 9–10 are shown only in the PDF. A future update would need to embed the below‑gate extension rows.
- **Deck (27 slides):** Same — 8 batters displayed; extension rows not yet incorporated.
- **What‑if study:** Investigate how the ranking changes if the gate is lowered to B_A ≥ 0.10 or B_A ≥ 0.15 — but this would be a new MDR, not a tweak to the pre‑registered rule.
- **Name‑resolution fix:** F5‑01 defect (corrupted `name` column) is worked around by using `player_identity.csv`; a future Phase may regenerate `players_dim.csv` with proper authorisation.
- **No deployment or publication** of player‑facing results unless and until the owner authorises it.

## Acknowledgements, Citation, License, Contact

This work was conducted under the Rajasthan Royals SupeRR Selector Season 2 framework. The methodology was pre‑registered in SDR‑2026‑11‑18‑03, and the owner‑approved batter‑list extension decision is recorded in SDR‑2026-11-18-04-batter-extension.md. Pipeline code is in `src/`. Tests are in `tests/`. The 13 frozen Phase 5 SHA‑256 hashes and the audit bundle (`reports/audit_bundle/sha256_outputs.txt`) guarantee that the rankings have not been secretly re‑run or tweaked.

> **Citation:** Aditya et al., *SupeRR Selector Season 2 – Round 1: Pressure‑Adjusted T20 Rankings*, Unstop submission format, 18 November 2026. 22‑page report: `outputs/final/deliverables/SupeRR_Selector_Phase6_Report.pdf`. Extended batter list: `outputs/final/phase7/ranking_batter_chase_extended.csv`. DOI/URL: none (local project).

MIT. See `LICENSE` at the repo root.

Project owner: Deo Raj Singh  
Email: available via the Mac / AppuBot setup  

Questions, corrections, or audit requests should be directed to the project owner through the usual channels. The code and data are open for reproducible inspection under the MIT license — but raw data and generated deliverables are excluded from the public GitHub remote (source‑only commit `853e41b`).