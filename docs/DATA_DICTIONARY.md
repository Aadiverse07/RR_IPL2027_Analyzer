# Data dictionary

This document describes the columns used by the dashboard and Phase 5 published outputs.
The CSV files remain local inputs and are not included in the public repository.

## Ranking fields

| Field | Meaning |
|---|---|
| `player_id` | Stable player identifier used to join score and identity records. |
| `player_name` | Display name resolved from the Phase 5 source-mapping verification. |
| `role` | `batter` or `bowler`. |
| `context` | Validated pressure context. Published rankings use `chase`; innings-1 bowling is separate. |
| `formats_present` | Competition formats represented in the player's evidence. |
| `rank` | Position by the approved point-score ordering within the eligible pool. It is not a statistical superiority claim. |
| `S_star` | Performance Score: `A_star - 0.30 * B_star`. |
| `S_ci90_low`, `S_ci90_high` | Lower and upper bounds of the match-aware 90% interval for `S_star`. |
| `A_star` | Shrunk pressure performance estimate. |
| `B_star` | Shrunk non-pressure baseline estimate. |
| `D_star` | Shrunk pressure-minus-baseline difference. |
| `shrinkage_A` | Reliability weight for the pressure record, `B_A`; eligibility requires at least 0.20. |
| `evidence_tier` | `Limited`, `Moderate`, `High`, or `Insufficient`, based on the reliability weight. |
| `n_pressure` | Pressure deliveries contributing to the estimate. |
| `pressure_matches` | Distinct matches with pressure evidence. |
| `consistency_positive_share` | Share of match-level pressure residuals above zero. |
| `bootstrap_share_top10` | Share of 200 match-block resamples in which the player remains in the published top ten, conditional on a fixed EB fit. |
| `bootstrap_rank_median`, `bootstrap_rank_p05`, `bootstrap_rank_p95` | Median and 5th/95th percentile ranks in those resamples. |
| `format_disagree` | Whether the format-specific evidence conflicts under the Phase 5 rule. |

## Interpretation

Performance Score and Reliability of Evidence answer different questions. `S_star`
describes modeled performance and orders the list. `shrinkage_A` describes evidence
strength and determines eligibility. They are not multiplied or merged. An interval
that contains zero does not rule out average pressure performance.

First-innings bowling uses a distinct, state-confounded context and has no eligible
players. Do not merge it with chase estimates. T20I-only eligibility is zero in both
roles; the combined format result is descriptive and does not support transferability.
