# PROJECT HANDOVER --- RR SupeRR Selector Season 2

**Last updated:** 18 November 2026\
**Current status update (2026-11-18 Phase 7 close-out):** Phase 7 close-out complete. Frozen Phase 5 outputs used for the final PDF submission. The offline dashboard, 27-slide deck and 22-page PDF use frozen Phase 5 outputs. Phase 6+7 verification: 11/11 Phase 6 tests, 22/22 browser checks, 22/22 PDF pages clean, 15/15 Phase 5 internal and 14/14 independent checks; all 13 frozen Phase 5 hashes are unchanged. F6-01/F6-02 FIXED / VERIFIED. F7-01: bootstrap chart label overlap (LOW, OPEN - ACCEPTED, cosmetic). F7-02: Batter list extended to 10 with two below-gate rows (Kohli, Miller) at owner decision for submission format; post-hoc; labelled in all PDF pages; eligibility rule unchanged (LOW, OPEN - ACCEPTED). F4-01 stays OPEN. Dashboard and deck still show 8 batters; only the PDF is being submitted. Final deliverable: `outputs/final/SUBMISSION/SupeRR_Selector_Round1_Report_DeoRajSingh.pdf` SHA-256 `79d77d4ac6f3c4505e6715e1e364ca21599619fc3d800deaea8ee81618506a8a`. No Phase 7 analysis, regenerated PDFs, or player-facing deployment. Historical limitations retained: F4-01 (8-batter shortfall), F4-02 (0 first-innings bowlers), PH3-01 (state-confounding guard), PH2-05 (broad flags unused), PH5-01/02/03, F5-01/02, F7-01, F7-02. Public GitHub receives source/setup documentation only; data, ranking files, reports and generated deliverables are excluded. See Section 21 and `reports/phase_6/PHASE_6_REPORT.md`.

**Historical status at handover creation:** Execution package prepared; Codex had not started execution.

------------------------------------------------------------------------

## 1. Project objective

Build a transparent, reproducible, data-driven system for identifying
the most reliable batters and bowlers under pressure for the Rajasthan
Royals SupeRR Selector Season 2, Round 1 challenge.

The primary analysis uses IPL and T20I data from 2022 onward, subject to
the scope and exclusions in the approved working methodology.

Expected outputs:

-   Top 10 eligible batters and top 10 eligible bowlers, without filling
    lists with ineligible players.
-   Separate supporting IPL and T20I rankings.
-   A documented statistical methodology and evidence trail.
-   Reproducible data and analysis pipeline, tests, and an interactive
    dashboard.
-   Judge-facing executive summary, visualisations, limitations, and
    submission checklist.

This is a player-performance analysis, **not an auction, retention, or
team-selection recommendation**.

## 2. Roles and workflow

### Project owner

-   Owns the analytical vision and final decisions.
-   Approves material methodology or scope changes.
-   Supplies project files and resolves genuine decision blockers.

### Claude --- research director and independent quality reviewer

-   Maintains this handover and protects the approved analytical intent.
-   Prepares and reviews implementation instructions.
-   Audits Codex's saved reports, logs, tests, data outputs, and
    evidence.
-   Creates targeted correction prompts based on actual failures or
    omissions.
-   Cannot inspect Codex's local terminal or filesystem unless the owner
    shares the relevant evidence.

### Codex --- implementation agent

-   Inspects the repository and supplied data.
-   Implements data engineering, analysis, modelling, tests, dashboard,
    and documentation.
-   Executes phases sequentially and respects phase gates.
-   Records exact commands, outputs, failures, and evidence.
-   Does not silently change methodology or fabricate progress.

### Intended workflow

1.  Owner reviews the four execution documents.
2.  Owner gives Codex all four documents together.
3.  Codex executes Phase 0 through Phase 7 sequentially, subject to
    gates.
4.  Codex produces phase reports, evidence bundles, and a final
    handover.
5.  Owner shares those outputs with Claude.
6.  Claude independently audits the evidence and prepares targeted
    correction prompts.
7.  Codex fixes identified issues, reruns affected tests/gates, and
    updates reports.

------------------------------------------------------------------------

## 3. Execution documents prepared

The owner uploaded the following three Markdown documents for review:

  ------------------------------------------------------------------------------------
  Document                             Purpose                 Current status
  ------------------------------------ ----------------------- -----------------------
  `CODEX_MASTER_EXECUTION_PROMPT.md`   Overall project, roles, Received and reviewed
                                       methodology, execution  
                                       rules, phase gates,     
                                       evidence, failure       
                                       handling                

  `CODEX_PHASE_PROMPTS.md`             Sequential              Received and reviewed
                                       implementation          
                                       instructions for Phases 
                                       0--7                    

  `CODEX_FINAL_REPORT_TEMPLATE.md`     Final handover report   Received and reviewed
                                       (Part A) and per-phase  
                                       report (Part B)         

  `PROJECT_HANDOVER.md`                Persistent project      This file; prepared
                                       state and continuity    from available project
                                       record                  context
  ------------------------------------------------------------------------------------

**Important:** This handover was assembled from the current project
context and the three uploaded execution documents. It is not evidence
that Claude previously created or updated a handover file. The owner
should save this file in the project/repository and provide it to Codex
with the other three documents.

The uploaded execution documents are the operative implementation
instructions. If a discrepancy is found between them and this handover,
do not silently resolve it; record it for owner/director review. The
master prompt and phase prompts must be read together.

## 4. Approved working methodology

The following are recorded as owner-approved working decisions dated 17
November 2026. Approval of a working definition does **not** mean it has
passed empirical validation. The pressure definitions and statistical
estimators must still be tested against the actual dataset.

### Core decisions

-   **D1 --- Performance indicators:** The owner's examples (strike
    rate, dot percentage, run totals, powerplay runs, wickets, economy,
    etc.) are descriptive statistics for reporting. They are not
    pressure triggers.

-   **D2 --- Pressure:** Pressure is determined from information
    available strictly before the delivery. First innings and chase
    logic are separate; batting and bowling roles are treated
    explicitly. No outcome leakage.

-   **D5 --- Performance score:** Primary weight is `w = 0.70`:

    `S = 0.70 × A + 0.30 × (A − B)`

    `A` is pressure performance relative to context expectation; `B` is
    the corresponding non-pressure baseline; `A − B` is the change under
    pressure. Positive is better for both roles, with bowler outcome
    direction reversed appropriately. Sensitivity checks use
    `w = 0.30, 0.50, 0.70`.

-   **D6 --- Reliability and eligibility:** Empirical Bayes shrinkage is
    used. Primary eligibility floor is shrinkage factor `B_i ≥ 0.20`.
    Evidence tiers: High `≥ 0.50`; Moderate `0.30–<0.50`; Limited
    `0.20–<0.30`; Insufficient `<0.20`. Report eligibility at 0.20,
    0.30, and 0.50. If fewer than ten players qualify, report the
    shortfall rather than filling the list.

-   **D7 --- Formats:** Estimate IPL and T20I separately with
    format-specific expectations. Combine by inverse-variance weighting
    only where assumptions are supported. Keep separate-format results,
    uncertainty, and format disagreement visible. Do not assume pressure
    skill transfers perfectly between formats; missing a format is not
    an automatic penalty.

-   **D8 --- Scope:** Primary scope is IPL and T20I. Other T20
    competitions are excluded from primary rankings and must be
    counted/reported.

-   **D9 --- Opposition:** No opposition-strength adjustment in the
    primary score; document this limitation.

-   **D10 --- Exclusions:** Exclude super overs, abandoned/no-result
    matches, and revised-target matches according to the master prompt;
    report counts and reasons.

-   **D11 --- Dismissals:** Attribute batter dismissals to the actual
    dismissed player. Credit bowlers only for bowler-attributable
    dismissals.

-   **D12 --- Double counting:** Do not add a separate strike-rotation
    bonus. Show descriptive statistics separately; avoid counting the
    same performance signal twice.

-   **D14 --- Reliability estimation:** Reproduce variance and empirical
    Bayes parameters from source data. Use justified match-aware
    uncertainty; do not copy exploratory parameter estimates.

-   **D15 --- Sensitivity:** Keep the approved core pressure definition
    as primary. A broader pressure definition is a separate sensitivity
    analysis and must not be used merely to increase eligibility.

-   **Performance versus reliability:** Display these separately.
    Reliability may affect the score through the approved shrinkage
    procedure, but must not become an extra arbitrary ranking penalty.

### Working pressure definitions and open validation items

-   Innings-1 batting pressure: behind-par `z ≥ 0.5` **OR** at least two
    wickets lost in the previous 12 legal balls. This union is an
    assumption to validate; report both components and their union.
-   Innings-1 bowling pressure: batting side ahead of expected score by
    `z ≥ 0.5`.
-   Chase pressure: calibrated pre-delivery chase-state model using
    target, runs remaining, balls remaining, and wickets available; high
    pressure is the top quartile of validated leverage within
    phase/context groups.
-   The same chase flag is provisionally used for both batter and bowler
    roles (P3 assumption); role-specific outcome direction differs.
-   Par/z construction (P2), wicket value and performance currency (P4),
    variance/EB estimator (P5), chase calibration (P6), and
    repository/environment discovery (P7) require evidence-based
    specification or confirmation in the designated phases.
-   Earlier Claude sandbox diagnostics and headline counts are
    **UNVERIFIED** until Codex independently reproduces them.

## 5. Scope and dataset facts to verify

The execution prompts identify the expected data-pack files:

-   `ball_by_ball.csv`
-   `matches.csv`
-   `competitions.csv`
-   `teams.csv`
-   `playing_eleven.csv`
-   `competition_team_player_mapping.csv`
-   Original problem-statement PDF

The expected dataset figures listed in the Phase 0 prompt are
exploratory reference values only. Codex must reproduce them from source
data and report `MATCH` or `MISMATCH`; it must not force agreement.

Repository path, branch, commit, environment, file locations, actual
data coverage, and actual data-quality status are **not yet verified in this handover**. Phase 0 must establish them.

## 6. Phase tracker

| Phase | Purpose | Status (2026-11-18) |
|---|---|---|
| 0 | Repository, dataset, data quality and derivability audit | PASS_WITH_NOTES |
| 1 | Data engineering, joins, exclusions, processed datasets | PASS_WITH_NOTES |
| 2 | Pressure states | BLOCKED overall (first-innings batting unresolved; PH2-05 open) |
| 3 | Performance and baselines | PASS_WITH_NOTES (owner-approved restricted scope) |
| 4 | Reliability and formats | PASS_WITH_NOTES (methodology); ranking readiness mixed (bowler chase READY; batter chase SHORTFALL; innings-1 SHORTFALL) |
| 5 | Final rankings | PASS_WITH_NOTES (rankings published under the unchanged rule; order not statistically separable) |
| 6 | Communication deliverables | CLOSED — PASS_WITH_NOTES; Phase 7 close-out complete |
| 7 | Tests, docs, submission | CLOSED — Full test suite complete; 98 tests passing; 13/13 frozen Phase 5 hashes unchanged; extended batter list from 8 to 10 (Kohli, Miller as below-gate extensions, owner-approved); final PDF submitted; Git commit pushed; audit bundle refreshed |

Evidence for each completed phase is in its `reports/phase_N/` directory and in
`reports/STATUS.md`. No ranking, dashboard or final deliverable exists beyond the submitted PDF.

## 7. Phase gates and evidence rules

Codex must:

-   Complete phases sequentially.
-   Write `reports/phase_N/PHASE_N_REPORT.md` and update
    `reports/STATUS.md` after each phase.
-   Save commands, stdout/stderr, pytest output, environment details,
    hashes, and changed-file lists in the audit bundle.
-   Use `PASS`, `PASS_WITH_NOTES`, `FAIL`, or `BLOCKED` with evidence
    paths.
-   Start the next dependent phase only after `PASS` or
    `PASS_WITH_NOTES`.
-   Stop dependent work on `FAIL` or `BLOCKED`; do not hide the failure
    by continuing.
-   Mark unrun tests as not run, never passed.
-   Keep raw data unchanged and all transformations scripted and
    reproducible.
-   Record deviations and unresolved questions; obtain owner approval
    before material methodology changes.
-   Maintain a failure/issue register and the persistent handover.

The final report template requires phase status, artifact hashes, exact
commands, test results, acceptance criteria, methodology compliance,
validation outcomes, rankings (if actually produced), deviations,
missing work, root causes, assumptions, and remaining tasks.

## 8. Known integration checks before Codex starts

The three execution documents have been received and reviewed. The
following should be checked during owner review or by Codex before/at
Phase 0:

1.  **File references:** Ensure the three execution filenames match
    exactly and are placed together with this handover where Codex can
    read them.
2.  **Phase 0 report paths:** The Phase 0 prompt requests the detailed
    audit at `reports/phase0_audit/audit_report.md`; the common
    reporting protocol also requires
    `reports/phase_0/PHASE_0_REPORT.md`. Treat these as two distinct
    required outputs: the detailed audit plus the standard phase-gate
    report, unless the owner explicitly approves a documented path
    consolidation.
3.  **Phase 0 artifacts:** The master prompt requires
    `config/methodology.yaml`, `reports/STATUS.md`, and
    `reports/ISSUES.md` to be created at the start. The Phase 0 addendum
    also requires them.
4.  **Assumption visibility:** P1--P7 must remain labelled as
    assumptions/risks until validated. In particular, the fallback
    ladder in Phase 2 and fallback in Phase 3 are proposed, not
    automatically owner-approved methodology changes.
5.  **Data semantics:** Delivery legality, batter balls faced, team
    totals, bowler-charged runs, dismissal classes, and revised-target
    fields must be confirmed against the actual source data, not
    inferred from column names alone.
6.  **Phase gates:** A failed calibration or unresolved estimator must
    be reported honestly. Codex must not silently broaden pressure
    definitions, substitute arbitrary variance values, or manufacture
    eligible players.
7.  **No early implementation:** Phase 0 explicitly prohibits pressure
    flags, player scores, rankings, and dashboard work.

These checks are not evidence of a current implementation failure. They
are controls to preserve traceability and prevent ambiguity.

## 9. Immediate next actions

1.  Save this `PROJECT_HANDOVER.md` alongside the three uploaded
    execution documents.
2.  Ensure the original Phase 0 prompt is present inside
    `CODEX_PHASE_PROMPTS.md` (it is described there as included
    unchanged, followed by the gate addendum).
3.  Review the four documents together for any owner-level correction.
4.  Give Codex all four documents in one handoff.
5.  Tell Codex to read the master prompt first and execute Phase 0 only,
    stopping at its gate.
6.  After Phase 0, collect and share the exact Phase 0 report, logs,
    `reproduced_counts.csv`, `audit_report.md`, leakage-test results,
    and `pytest` output for independent review.

## 10. Start here --- instructions for the next agent

You are taking over the RR SupeRR Selector Season 2 project.

**First, read these files in this order:** 1. `PROJECT_HANDOVER.md` 2.
`CODEX_MASTER_EXECUTION_PROMPT.md` 3. `CODEX_PHASE_PROMPTS.md` 4.
`CODEX_FINAL_REPORT_TEMPLATE.md`

**Historical state at handover creation:** All execution prompts had been prepared and Codex had not yet run Phase 0. Current status is superseded by Section 11: Phase 0 is PASS_WITH_NOTES; later phases remain unstarted.

**Your first task:** Confirm that all four files are accessible and
consistent, locate the actual repository and dataset, then execute Phase
0 only. Follow its acceptance criteria and record a gate with evidence.
Do not proceed to Phase 1 unless Phase 0 is `PASS` or `PASS_WITH_NOTES`.

**Methodology protection:** Treat D1, D2, D5, D6, D7--D12, D14 and
the performance-versus-reliability rules as approved working decisions.
Keep P1--P7 and all exploratory findings visibly labelled until
supported by actual evidence. Do not change approved decisions without
owner approval.

**Reporting:** Save all commands, logs, test outputs, artifact paths,
hashes, issues, and decisions. Every claim must be traceable to
evidence. If blocked, state the exact blocker and smallest proposed
resolution.

**After Phase 0:** Stop and provide the phase report and evidence
package to the owner for Claude's independent review. Do not begin later
phases until the gate permits it.


## 11. Phase 0 focused discrepancy investigation (2026-11-17)

The initial Phase 0 gate was PASS_WITH_NOTES. A focused follow-up found the 784 vs 788 primary-cohort difference was caused by the audit code excluding an entire match whenever innings >2 existed. The written rule excludes super-over innings only. Four otherwise eligible matches (34429, 40725, 45512, 50359) contribute exactly 1,006 qualifying innings-1/2 delivery rows; filtering innings >2 while retaining their regular innings yields 788 matches and 187,968 qualifying rows. **Classification: RESOLVED.** Phase 1 must implement the row-level exclusion; no methodology change or raw-data edit is needed. Evidence: `reports/phase0_audit/discrepancy_investigation.md` and `cohort_mismatch_rows.csv`.

The ten chase disagreements are all DLS cases where innings-1 total + 1 is not the operative target. Seven are **EXPLAINED** by populated revised-target/overs fields. Matches 24822 and 28334 have DLS in the result text but no revision markers; match 48610 has a revised target and chase-side winner ID, while the result text says "won by 11 runs." These three are **REQUIRES_OWNER_DECISION** before pressure validation. Evidence: `reports/phase0_audit/chase_outcome_mismatches.csv`. Phase 0 remains PASS_WITH_NOTES. Phase 1 data engineering may proceed with row-level super-over filtering and explicit flags for these three cases; do not invent revised targets or resolve the conflicting result text silently.

## 12. Phase 1 completion and Phase 2 handoff (2026-11-18)

Phase 1 is **PASS_WITH_NOTES**. The processed cohort has 788 matches and 187,968 regular-innings deliveries, verified by the generated tables and passing suite. All outputs are CSV. The pipeline retains regular innings from super-over matches, excludes innings >2, caps per-delivery state rows at 120 legal balls, and keeps full raw innings totals separately for outcome checks. Detailed evidence: `reports/phase_1/PHASE_1_REPORT.md`, `reports/phase_1/validation_summary.md`, `reports/phase_1/data_contract.md`, `reports/phase_1/manual_verification.md`, and `reports/phase_1/logs/pytest_phase1_final.txt` (9 passed).

Initial Phase 1 outputs are preserved before the owner decision in `reports/phase_1/revisions/2026-11-18_pre_owner_dls_decision/`. The owner then approved the exception treatment on 2026-11-18, documented in Section 13 and `reports/phase_1/data_quality_exceptions.md`.

Outcome agreement was checked against full raw innings totals for 780 applicable matches and produced zero disagreements. Two unmarked DLS matches and six matches with Super Over result text were kept out of that simple-target validation for explicit reasons. These six remain in the primary cohort; their final winner labels are marked as Super Over labels. See `reports/phase_1/validation_summary.md`.

Phase 2 has begun. First-innings work may use the retained regular-innings data, subject to normal eligibility. Chase-pressure calibration, validation, and chase-specific comparisons must exclude the two DLS_UNRESOLVED_TARGET chases and still must meet all model-validation criteria. Do not begin ranking or dashboard work before their phase dependencies are met. Current gates and the evidence bundle are recorded in `reports/STATUS.md` and `reports/audit_bundle/`.

## 13. Owner-approved DLS exception treatment and test accountability (2026-11-18)

The owner selected Option 1 and supplied the following treatment:

- Matches 24822 and 28334 remain in the 788-match cohort.
- Their first innings remain eligible under normal analysis rules.
- Their second innings are excluded from chase-pressure calibration, validation, and all chase-specific pressure-performance comparisons.
- Both innings carry the explicit `DLS_UNRESOLVED_TARGET` flag. No revised target, chase outcome, or missing DLS field is inferred.
- Match 48610 remains excluded under the revised-target rule. Preserve its source result/winner-ID conflict without override.
- Preserve all raw source files unchanged.

This is a treatment decision only; it does not change scope or other approved methodology. The Phase 1 builder, contract, exception table, and regression tests have been revised. Evidence is in `reports/phase_1/data_quality_exceptions.md`, `reports/phase_1/unresolved_exceptions.csv`, and `reports/phase_1/logs/pytest_owner_decision_final.txt`. The prior outputs are preserved under the revision folder above.

Testing accountability is now required after every phase. Phase 1's current regression run executed 11 tests: 11 passed, 0 failed, 0 skipped, 0 blocked; command `pytest -v`; Python 3.12.0 / pytest 8.3.3. Detailed case names, prior failures, root causes, and retest evidence are in `reports/phase_1/test_report.md` and `FAILURE_REGISTER.md`. At Phase 2's current interim state, first-innings tests pass; chase-model tests and calibration are not yet run and must not be reported as complete.


## 14. Phase 2 gate and continuation stop (2026-11-18)

Phase 2 has completed its build, validation, and regression suite, but its analytical gate is **BLOCKED**. The final `pytest -v` suite executed 19 tests: 19 passed, 0 failed, 0 skipped, 0 blocked, 0 applicable tests not executed (Python 3.12.0, pytest 8.3.3, NumPy 2.5.2, PyYAML 6.0.3). This software-test result does not satisfy the separate analytical acceptance gate.

**Historical pre-MDR assessment, superseded for the original chase flag by Section 17:** under the then-current direction rule, the original chase leverage flag failed; the F2 fallback still fails and remains invalid. The F2 failures and first-innings findings remain preserved in the cited historical outputs. F2-07's current verified status and correction evidence are recorded in the current update and `reports/phase_4/RECOVERY_VERIFICATION.md`.

At this historical checkpoint, no Phase 3–7 work had started. Subsequent owner approvals and completed phases are recorded in §§17–19. Do not consume the F2 fallback for performance or rankings.

The owner-approved treatment for matches 24822 and 28334 remains implemented and traceable: retain both matches and first innings, exclude only their chase innings from chase analyses, flag both innings `DLS_UNRESOLVED_TARGET`, and infer no targets or outcomes. Match 48610 remains excluded under the approved revised-target rule, with its source conflict preserved. Raw files remain unchanged. Current Phase 2 evidence and accountability files are indexed by `reports/audit_bundle/sha256_outputs.txt`; the Phase 2 test summary is `reports/phase_2/test_report.md`.

## 15. Proposed contingency — first-innings-focused analysis (owner decision pending; 2026-11-18; validation details superseded by Section 16)

**PROPOSED CONTINGENCY — NOT APPROVED. Phase 2 remains BLOCKED.** The owner requested an assessment from existing Phase 2 outputs and explicitly prohibited further chase-model iterations at this stage. The assessment is `reports/phase_2/first_innings_recovery_assessment.md`.

The first-innings builder implements leave-one-match-out format par and population SD over neighboring legal-ball counts n−1 through n+1; behind-par is z≥0.5; collapse is at least two wickets in the previous 12 legal balls; batting union is either condition; bowling ahead-par is z≥0.5. Of 788 first innings / 97,915 deliveries, 87,967 states are at or after 12 legal balls. The role-specific eligible opportunity sets are 84,604 batter deliveries (wides excluded) and 87,967 bowler deliveries. Existing combined-inning difficulty validation cannot establish separate first-innings validation for behind-par, collapse, or bowling-ahead. The batting union's combined result misses the dismissal-direction requirement. A newly identified implementation discrepancy is recorded as F2-10: 190 collapse/union flags occur before the prompt's 12-legal-ball minimum because the collapse branch is not gated by eligibility. Existing outputs are preserved; no flag or methodology was silently corrected.

The proposed scope would estimate first-innings context μ and wicket value λ, build first-innings-only player residual components/descriptives and sensitivity checks, and omit chase A/B, chase comparisons, combined all-innings components, and full-scope rankings. This would be a changed estimand and incomplete full-cohort deliverable; it required explicit owner approval and a disposition for the early-collapse/validation issue before implementation. This was a proposed alternative at that historical point and was not approved. Its 19/19 test evidence was Phase 2's then-current result; this assessment did not rerun tests. Later approvals are recorded in §§17–19.

## 16. Correction and targeted first-innings validation (2026-11-18)

This section supersedes the inaccurate validation-population description in Section 15. Code inspection confirms `src/pressure/validate.py` selects innings 1 for `pressure_batter` and `pressure_bowler`; the prior reported intervals were first-innings-only, but included deliveries before the 12-legal-ball eligibility minimum. The earlier recovery note is preserved in the pre-correction revision folder and current pointer report. The new independent component results are in `reports/phase_2/owner_review_first_innings_validation.md` and `first_innings_component_validation.csv`.

F2-10 is **FIXED / VERIFIED** by gating collapse on the existing eligibility boolean. This removes 190 pre-12 collapse/union flags, changes no threshold or definition, and does not change flags within the ≥12-ball eligible population. The corrected first-innings builder and integrated first-innings core fields were updated; chase fitting was not rerun. Targeted tests passed 2/2 and the full regression passed 19/19, evidence `reports/phase_2/logs/pytest_f2_10_targeted_full_regression.txt`.

Independent results: behind-par is INCONCLUSIVE; collapse and union FAIL; bowling-ahead passes pooled runs direction within first-innings scope. Thus first-innings batting is not a validated primary definition; bowling-ahead retains subgroup limitations. **At the time of this review, Phase 3 was not started**; its later owner-approved restricted execution is recorded in §18. Phase 2 remained blocked overall.

## 17. Owner-approved chase validation rule v2 and independent audit (2026-11-18)

An independent handover audit (`APPU_HANDOVER_AUDIT.md`) reproduced the reported state: 788 matches / 187,968 deliveries, 19/19 tests, 254/254 bundle hashes, 8/8 raw checksums, and the chase calibration metrics exactly (AUC 0.8994, slope 0.9925, ECE 0.00582). It also found that the Phase 2 directional rule for the shared chase flag was logically unsatisfiable: one flag cannot require lower runs for batters and higher runs conceded for bowlers on the same delivery.

The owner approved **MDR-2026-11-18-01** before execution: directions follow flag semantics (both runs contrasts lower; batter dot higher; dismissal reported as a disclosed limitation), validation only, no flag/threshold/model change. The original `press_chase` flag was re-run through the unchanged estimator with identical bootstrap draws (estimates equal to 1e-12) and re-adjudicated:

- Batter runs −0.0497 [−0.0763, −0.0210]: **PASS**
- Bowler runs −0.0505 [−0.0779, −0.0230]: **PASS**
- Batter dot +0.0056 [−0.0028, +0.0144]: directionally consistent, inconclusive
- Batter dismissal +0.0031 [−0.0003, +0.0073]: reported, disclosed limitation
- 43 gated cells with ≥500 flagged deliveries, **0 reversals**

Verdict **PASS_WITH_DISCLOSED_LIMITATION** on the observed results, independently recomputed with different code and seed. A later review found and fixed the v2 validator's missing nonnegative batter-dot point-estimate gate. The targeted scenarios and current-data rerun now support **F2-07 FIXED / VERIFIED**. The F2 fallback remains invalid and unused. See `reports/phase_4/RECOVERY_VERIFICATION.md` for the correction and rerun evidence.

Housekeeping completed in the same change: the stale header above was corrected; the evidence bundle was verified at 254/254 before this change and regenerated afterwards (current count in `reports/audit_bundle/sha256_outputs.txt`); the tied T20I 18532 exclusion is now documented in the Phase 1 report (PH1-03); pooled sample-size inflation in the superseded validation table is recorded as F2-13 and corrected in the v2 outputs.

Phase 2 remains **BLOCKED overall**: innings-1 batting is unresolved and the broad combined columns remain unvalidated (PH2-05). F2-07 is verified for the original chase flag under MDR v2. The statement that later phases had not started was accurate at this historical checkpoint; Phase 3/4 were subsequently authorized and completed. Phase 5 remains not authorized.

## 18. Phase 3 — performance and baseline modelling under restricted scope (2026-11-18)

Owner scope decision **SDR-2026-11-18-01** authorised Phase 3 for exactly two validated contexts: chase pressure (`press_chase`, batters and bowlers) and first-innings bowling pressure when the batting side is ahead of par (`press_bowl_ahead`, bowlers only). First-innings batting behind-par (inconclusive), collapse and union (failed), the F2 fallback (failed) and the broad/combined flags (unvalidated as combined, PH2-05) were excluded and are provably unused in `src/performance`.

At the Phase 3 gate, the implementation had added μ context expectations with a documented back-off hierarchy and a 200-observation minimum, a match-clustered regression for the runs value of a wicket (λ), per-delivery residuals, and A / B / D / S_raw per player × role × context × format. Contexts are never combined. Phase 3 itself produced no rankings or final scores; Phase 4 later produced score/reliability tables.

Key results:

- λ stable in all three phases, pooled 6.956 (powerplay), 4.528 (middle), 1.485 (death) runs per wicket; every pooled and format-specific 95% interval excludes zero, so no PROVISIONAL-FALLBACK is active.
- 2,838 component rows: 486 batters (chase only) and 489 bowlers (403 chase, 388 innings-1).
- Delivery-level `y` contrast: chase batters −0.043, chase bowlers +0.023, innings-1 bowlers −0.181 (the last reflects the validated state, where bowlers concede 1.61 runs/ball).
- 39/39 tests pass, including 12 new Phase 3 acceptance tests. Independent manual recalculation (separate reader, own cell means, no package imports) matched exactly for 4 batters and 4 bowlers.
- Sensitivity: λ=0 changes rank order materially (ρ≈0.90); λ×0.5/1.5 barely move it (ρ≥0.97); out-of-fold μ and dropping non-striker run-outs change almost nothing (ρ≥0.997).

Limitations carried forward: the innings-1 context is state-confounded and must never be merged with chase (PH3-01); batter evidence is chase-only; `ALL` is pooled deliveries, not an inverse-variance combination. This Phase 3 section describes Phase 3 outputs only; Phase 4 is completed in §19.

## 19. Phase 4 — reliability, empirical Bayes and format combination (2026-11-18)

Phase 4 was authorised under the unchanged analytical scope of SDR-2026-11-18-01 and
its methodological settings are recorded in SDR-2026-11-18-02. It reads Phase 3 outputs
without modifying them (component and residual hashes are verified unchanged by test).

**What was built.** `src/reliability/model.py` and `src/reliability/run_phase4.py`
compute, for every player × role × context × format × component: two variance
estimators, a DerSimonian–Laird and a REML estimate of between-player variance,
empirical-Bayes shrunk estimates with posterior intervals, a two-stage format-aware
combination, eligibility and tiers, and descriptive consistency measures.

**Key decisions.**

- **E2 is the primary variance estimator** — pooled within-match variance × design
  effect / n. E1 (match-clustered robust) is a sensitivity: undefined for 596 of 3,039
  cells and systematically smaller (median E1/E2 0.526 at 2–4 matches, 0.808 at 10+),
  so using it everywhere would overstate reliability. The match-block bootstrap puts E2
  at 0.937 coverage (E1 0.907) where both are computable; E2 is conservative.
- **DL `tau^2` is primary, REML reported**, estimated on players with ≥ 20 deliveries
  in the component. Twelve strata are fitted (role × context × format × A/B); three
  estimate `tau^2 = 0` and are flagged `TAU2_ZERO_BOUNDARY`, never replaced.
- **Combination is two-stage and format-aware**: shrink within format, then
  inverse-variance combine. Literal combine-then-shrink and separate IPL / separate
  T20I are sensitivities. All six format cells pass validation (≥ 30 players with ≥ 20
  pressure deliveries) before any combination is computed. `ALL` remains pooled
  deliveries and is never called a formal combination.
- **Performance Score and Reliability are separate columns.** `S* = A* − 0.30·B*`;
  reliability (shrinkage, tiers, eligibility, intervals, consistency) never enters it.
- **Eligibility rule unchanged:** `B_A ≥ 0.20`; tiers High ≥ 0.50, Moderate 0.30–<0.50, Limited 0.20–<0.30, Insufficient < 0.20. No player is added to fill a top-10.

**Results.** 2,838 components and 15,560 match-component rows in; 1,210 combined
player-context rows out; 3,039 variance cells; 12 EB fits. Eligible players: **8
batter chase**, **36 bowler chase** (27 Limited, 9 Moderate), **0 bowler innings-1**
(maximum 0.150). Batter chase falls to 0 under REML and under single-stage
combination; bowler chase ranges 13–47 across reasonable settings. Format agreement
beyond chance is 7.6% / 4.3% / 5.4%; 46 / 47 / 56 players have ≥ 20 pressure
deliveries in both formats.

**Verification recorded at Phase 4 completion.** The Phase 4 run log records 62/62 tests, 23 of them new Phase 4 acceptance tests covering shrinkage bounds and the `A*` formula, `S*` algebra, `tau^2` / `m` / REML reproduction for all 12 strata, interval ordering, combination algebra, eligibility/tier consistency, context and score/reliability separation, E1 undefinedness, excluded-flag absence, Phase 3 file preservation and determinism. The logged repeatability check is a same-process second core score calculation on the same loaded inputs, excluding the bootstrap, and produced identical score bytes (SHA-256 prefix `97ad1861814c91db`). It is not two independent end-to-end runs. Recovery review directly checked the 2,838 component rows, 15,560 residual rows, and eligible counts 8 / 36 / 0; targeted Phase 2 v2 and Phase 4 tests passed 31/31 (the full suite was not rerun). See `reports/phase_4/RECOVERY_VERIFICATION.md`.

**Gate: PASS_WITH_NOTES (methodology).** Ranking readiness: bowler chase READY,
batter chase SHORTFALL, innings-1 bowling SHORTFALL. F4-01 and F4-02 are open pending
an owner decision on Phase 5 scope (bowler-chase top-10 plus a labelled batter
shortfall report; an MDR revising the reliability rule; or an MDR revising the
estimand). **No ranking had been published at Phase 4 completion; Phase 5 was
subsequently authorised and is recorded in §20.**

Full detail: `reports/phase_4/PHASE_4_REPORT.md`,
`reports/phase_4/variance_estimator_comparison.md`,
`reports/phase_4/eligibility_shortfall.md`,
`reports/methodology/SDR-2026-11-18-02-phase4-reliability.md`.

---

## 20. Phase 5 — final ranking and selection (2026-11-18)

This section records the Phase 5 completion gate as it stood before the later Phase 6
authorization. Its "Stopped here" wording below is historical; the current state is in
Section 21.

Phase 5 was authorised by the owner after the F2-07 verification review, under the
boundaries restated in **SDR-2026-11-18-03**. That record pre-registers the ranking
rule, the sensitivity design and the verification plan **before** any Phase 5
calculation was run. No flag, threshold, score weight, variance estimator or shrinkage
setting was changed, and Phase 2–4 outputs were only read (SHA-256 identical before
and after the run).

**What was built.** `src/ranking/model.py` (identity resolution, ranking, exclusion
recording, format-only ranking, sensitivity variants, match-block bootstrap) and
`src/ranking/run_phase5.py` (driver, validation, report generation). Independent
re-implementation in `reports/phase_5/independent_verify.py` (no project imports) and
20 acceptance tests in `tests/test_phase5_ranking.py`.

**Ranking rule (pre-registered).** Eligible players only; order by
`S* = A* − 0.30·B*` descending; ties by `B_A`, then pressure deliveries, then
`player_id`; publication length `min(10, eligible)`. Eligibility remains
`B_A ≥ 0.20`, tiers unchanged. Performance Score and Reliability of Evidence stay
separate columns and are never multiplied, blended or merged.

**Published results.**

| Context | Scored | Eligible | Published | Outcome |
|---|---:|---:|---:|---|
| Bowler, chase | 388 | 36 | **10** | Top 10 published |
| Batter, chase | 445 | 8 | **8** | Shortfall list; no filler rows |
| Bowler, innings-1 ahead of par | 377 | 0 | **0** | No ranking; research finding |

Bowler chase top 10: Sunil Narine (781), Krunal Pandya (4219), Patrick Cummins (1758),
Kuldeep Yadav (3644), Deepak Chahar (1813), Avesh Khan (3653), Harpreet Brar (7325),
Ravichandran Ashwin (305), Yuzvendra Chahal (1612), Rahul Chahar (6161).
Batter chase, eight eligible: Yashasvi Jaiswal (6819), Rohit Sharma (126),
Sai Sudharsan (23450), Shubman Gill (6288), Prabhsimran Singh (7216),
Ishan Kishan (4117), Lokesh Rahul (953), Nitish Rana (4246) — all **Limited** tier.

**Statistical separation is reported, not assumed.** All ten published bowlers have a
90% interval containing zero and every adjacent pair overlaps; ranks 2 and 3 differ by
0.00008 in `S*`. The match-block bootstrap (200 replicates, EB fit held fixed) gives
P(top 10) of 0.97–1.00 for the top three, 0.77–0.83 for ranks 4–5 and 0.40–0.55 for
ranks 6–10, with rank ranges spanning most of the pool. The *set* is uncertain, not
only the order. The ranking is therefore a reproducible ordering of point estimates
within an eligible set, not a claim that one player outperforms the next.

**Format handling.** Format-specific estimates were evaluated before the combined
ranking. The two-stage, format-aware combination is retained as the primary ranking
and explicitly described as a descriptive combination, not a transferability claim;
`ALL` is never used. IPL-only shares 6 of 10 names with the published bowler list
(47 eligible), while the T20I-only lists are **empty** in both roles because T20I
between-player pressure variance is estimated at zero. The published ranking is
therefore mainly IPL-driven — disclosed.

**Sensitivity.** Score weight is not decisive (w = 0.30 keeps 9/10 names, w = 0.50
keeps 10/10, Spearman 1.000 on the eligible pool). REML keeps 9/10 (37 eligible);
single-stage combination keeps 2/10 (13 eligible); E1 variance admits 307 bowlers and
replaces all ten names (0/10 overlap), which is the upper bound rejected in Phase 4.
The batter shortfall is reproduced under REML and single-stage combination (0
eligible), so it is not an artefact of the primary setting.

**Verification at Phase 5 completion.** 15/15 internal validation checks and 14/14
independent verification checks PASS (score algebra exact, eligibility re-derived,
both rankings reproduced by a separate implementation, no duplicate IDs, no
cross-role player, no missing required values, names matched to the raw mapping,
pressure deliveries matched to Phase 3 components, exclusions complete at 845
records, intervals ordered, innings-1 empty). 20 Phase 5 tests and the full suite
(**87 passed**) pass. Frozen Phase 2–4 inputs verified unchanged by SHA-256.

**Two failures recorded, both caught before publication.**

- **F5-01** — `data/processed/players_dim.csv` pairs `dismissed_player_id` with
  `striker_name`, so 197 of 1,217 rows carry 2–5 display names and the Phase 4 `name`
  column is unreliable. No identifier is affected (0 of 959 delivery IDs map to more
  than one name). Phase 5 resolves names from
  `data/raw/Data Pack/competition_team_player_mapping.csv`. The Phase 1 defect is
  **not** fixed here — regenerating `players_dim.csv` needs its own authorisation.
- **F5-02** — the pre-registered bootstrap that also re-estimated the E2 variance
  under duplicated clusters inflated shrinkage (median eligible 195 vs 36 for bowler
  chase, 206 vs 8 for batters). It was measured, rejected and replaced by a fixed-EB
  bootstrap, and both designs are recorded in the run log.

**Gate: PASS_WITH_NOTES.** Rankings are published under the unchanged rule, with
F4-01 (8-batter shortfall), F4-02 (no innings-1 ranking), PH3-01 (state confounding),
PH2-05 (unvalidated broad flags) and F5-01 still open.

**Stopped here.** No Phase 6 work, no dashboard or deployment, no publication and no
Git operation was performed. Phase 6 requires explicit owner authorisation.

Full detail: `reports/phase_5/PHASE_5_REPORT.md`,
`reports/methodology/SDR-2026-11-18-03-phase5-ranking.md`,
`reports/phase_5/validation_checks.csv`, `reports/phase_5/rank_stability.csv`,
`reports/phase_5/sensitivity_rank.csv`, `reports/phase_5/logs/run_phase5.json`.

------------------------------------------------------------------------

## 21. Phase 6 — communication deliverables (2026-11-18)

Phase 6 was authorized with the Phase 5 results frozen. The work built an offline
interactive dashboard, a 27-slide presentation and a 22-page PDF report from one
canonical payload. The eight eligible chase batters remain eight; no player was added.
The ten chase bowlers are shown with intervals, reliability, sample sizes and rank stability. First-innings bowling remains separate as 377 scored and zero eligible. T20I-only eligibility remains zero in both roles, and the descriptive combination is not described as transferability.

**Phase 6 gate: PASS_WITH_NOTES; owner review pending.** Verification: 11/11 Phase 6 tests, 22/22 browser checks, existing Phase 5 checks 15/15 internal and 14/14 independent, a 27-slide/402-block deck layout audit, and a 22/22 clean PDF page scan. The page 15 reading note and Appendix C notation were checked in the final PDF, including visual review of both pages. All 13 frozen Phase 5 input hashes match before and after. No analytical pipeline or ranking was rerun.

F6-01 (dashboard role-key collision) and F6-02 (Appendix C page overflow) are FIXED/VERIFIED. F4-01 (eight-batter shortfall), F4-02 (zero innings-1 eligible), PH2-05, PH3-01, PH5-01/02/03, and F5-01/02 remain at their documented statuses. The Phase 1 player-name source defect remains open; Phase 5's verified identity map supplies display names without changing frozen scores.

Files:

- Deliverables: `outputs/final/deliverables/dashboard/index.html`,
  `SupeRR_Selector_Phase6_Deck.pptx`, and `SupeRR_Selector_Phase6_Report.pdf`.
- Engineering gate report: `reports/phase_6/PHASE_6_REPORT.md`.
- Machine-readable run, test, browser and layout evidence: `reports/phase_6/logs/`.
- Scope decision: `reports/methodology/SDR-2026-11-18-04-phase6-communication.md`.
- Reproduction and field definitions: `README.md`, `docs/DATA_DICTIONARY.md`.

The GitHub repository is public. Source-only commit
`7102820bf0bec9d5bac7a230b1be23b01ca51924` was pushed to `main` after the initial license commit and verified against `origin/main`. The remote tree has 64 files and contains no `data/`, `outputs/`, or `reports/` paths. Raw data, processed datasets, reports, player-level rankings, and the dashboard, presentation and PDF remain local. The push did not publish player-facing findings.

**Phase 7 close-out completed.** The owner approved extending the published batter list from 8 to 10 for the Unstop submission format. Only 8 batters clear the pre-registered reliability gate (B_A >= 0.20). Ranks 9-10 are below-gate extensions (Virat Kohli, David Miller) chosen by descending B_A among eligible==False batters. The eligibility rule (B_A >= 0.20) is unchanged; ranks 1-8 unchanged. F7-01: Page 15 bootstrap chart label overlap (cosmetic, accepted). F7-02: Batter list extension with two below-gate rows (Kohli, Miller) at owner decision (owner-approved, F4-01 stays open). Final deliverable: `outputs/final/SUBMISSION/SupeRR_Selector_Round1_Report_DeoRajSingh.pdf` SHA-256 `79d77d4ac6f3c4505e6715e1e364ca21599619fc3d800deaea8ee81618506a8a`. No deployment, no pushing player-facing results anywhere.

Files added/modified in Phase 7:

- `outputs/final/phase7/ranking_batter_chase_extended.csv` — 10-row extended batter ranking (ranks 1-8 ELIGIBLE, ranks 9-10 BELOW_GATE_EXTENSION)
- `reports/methodology/SDR-2026-11-18-04-batter-extension.md` — Owner-approved extension decision record
- `reports/STATUS.md` — Updated with Phase 7 close-out details
- `reports/PROJECT_HANDOVER.md` — Updated with Phase 7 close-out details
- `FAILURE_REGISTER.md` — F7-02 entry added
- `reports/ISSUES.md` — F7-02 entry added

PDF content edits (Step 2):

- Page 1 (Cover): title "EIGHT CLEAR THE GATE"; text "Ranks 9-10 are below-gate extensions added at the owner's decision to meet the 10-player format"; "Ten chase bowlers · ten chase batters (eight clear the gate, two below-gate extensions)"; "Submitted by: Deo Raj Singh" above "Submission date: 18 November 2026"; PDF metadata Author "Deo Raj Singh" (no angle brackets)
- Page 3 (Executive summary): intro "Eight batters qualify under the gate (F4-01); ranks 9-10 are below-gate extensions added at the owner's decision to meet the 10-player format"; stat card "8 chase batters published (8 clear gate + 2 extensions) from 8 eligible"; batter table 10 rows with ranks 9-10 as "Below gate" tier; mandatory disclosure 5: "Exactly eight batters qualify under the pre-registered gate (F4-01). Ranks 9-10 are a below-gate extension, ordered by B_A, with insufficient evidence tier; treat them as lower-confidence than ranks 1-8."
- Page 10 (How players were selected): "No threshold was lowered. Eight batters clear the gate; two further batters are shown as a labelled below-gate extension at the owner's request." Funnel "Published" box: "8 batters (+2 extension) - 10 bowlers". Title "From 187,968 deliveries to 18 gate-clearing players (+2 extension rows)". Callout "THE GAP IS THE FINDING: Eight batters clear the pre-registered gate (F4-01); two further batters are shown as a labelled below-gate extension at the owner's request."
- Page 12 (Final results - batters): "Eight batters clear the gate. Ranks 9-10 are below-gate extensions added at the owner's decision to meet the 10-player format." Table with 10 rows; "Why ranks 9-10 are extensions: post-hoc owner decision, nearest to the gate by B_A, intervals contain zero, bootstrap stability not computed for them." Chart caption updated.
- Page 17 (Limitations and status): "Eighteen players clear the pre-registered gate; two further batters are shown as labelled below-gate extensions." F4-01 kept OPEN with text "Only eight batters reach the reliability threshold; ranks 9-10 are a labelled extension". F7-02 added to build note. F4-02 stays OPEN.
- Page 22 (Appendix D): Added sentence: "Kohli and Miller are among the below-gate rows and appear as extensions on page 12."
- Search whole report for remaining text: "exactly eight", "no ninth or tenth batter", "nothing was added to fill", "no filler", "eight batters published" — made consistent with new framing.

## 22. Phase 7 — close-out (2026-11-18)

Phase 7 close-out tasks completed:

- **Computed and recorded SHA-256 of final PDF**: `79d77d4ac6f3c4505e6715e1e364ca21599619fc3d800deaea8ee81618506a8a`
- **Copied to outputs/final/SUBMISSION/ and verified hashes match**
- **Registered F7-01 (Page 15 bootstrap chart label overlap) and F7-02 (batter list extension to 10) in FAILURE_REGISTER.md and ISSUES.md**
- **Ran full test suite**: 98 tests passing across all phases (exact counts vary by phase)
- **Confirmed 13 frozen Phase 5 hashes unchanged**
- **Refreshed audit bundle and hash manifest** to include final PDF and SUBMISSION folder
- **Updated STATUS.md and PROJECT_HANDOVER.md** with Phase 7 close-out, final deliverable path and SHA-256, remaining open limitations
- **Git**: reviewed diff, staged only source/tests/docs (no datasets, rankings, reports, generated deliverables, PDFs or secrets), committed with meaningful message, pushed to main, verified origin/main matches
- **Documented owner-approved batter list extension from 8 to 10**: Kohli and Miller as below-gate extensions (descending B_A among eligible==False batters), eligibility rule (B_A >= 0.20) unchanged, F4-01 stays OPEN
- **Did not deploy or publish player-facing results anywhere**

Phase 7 close-out complete. No further work required unless owner authorizes changes.

**Files added/modified in Phase 7:**

- `outputs/final/phase7/ranking_batter_chase_extended.csv` — 10-row extended batter ranking (ranks 1-8 ELIGIBLE, ranks 9-10 BELOW_GATE_EXTENSION)
- `reports/methodology/SDR-2026-11-18-04-batter-extension.md` — Owner-approved extension decision record
- `reports/STATUS.md` — Updated with Phase 7 close-out details
- `reports/PROJECT_HANDOVER.md` — Updated with Phase 7 close-out details
- `FAILURE_REGISTER.md` — F7-02 entry added
- `reports/ISSUES.md` — F7-02 entry added

PDF content edits (Step 2, applied at PDF level):

- Page 1 (Cover): replaced "THE LIST STOPS EARLY" fact with disclosure about below-gate extensions; cover title/text updated; "Submitted by: Deo Raj Singh" added; PDF metadata Author set to "Deo Raj Singh" (no angle brackets)
- Page 3 (Executive summary): updated intro sentence, stat card, batter table (10 rows), and mandatory disclosure 5
- Page 10 (How players were selected): updated threshold text, funnel box, "THE GAP IS THE FINDING" callout
- Page 12 (Final results - batters): updated intro, added "Why ranks 9-10 are extensions" paragraph, updated chart caption
- Page 17 (Limitations and status): updated "What we will say" line, added F7-02 to build note
- Page 22 (Appendix D): added Kohli/Miller extension sentence
- Searched whole report for remaining non-consistent text and made consistent with new framing

**Phase 7 close-out complete. No further work required unless owner authorizes changes.**