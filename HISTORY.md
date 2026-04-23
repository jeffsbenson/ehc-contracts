# ehc-contracts — History

Dated entries for shared metrics, fixtures, and schemas. For current
rules and the package layout, read `README.md` and each module's
docstring. Entries in reverse chronological order.

---

## 2026-04-23 — Phase 6 (EHC Federation Cohesion Plan) — docstring follow-on

Phase 6 (2026-04-23): one-line docstring fix in
`ehc_contracts/metrics/lots_on_delay.py`. The authoritative-spec pointer
referenced the former `Project_Financials_Data_Dictionary.xlsx` "Lots
on Delay Logic" sheet, which was deleted as part of Phase 6. The
docstring now points to the BMD Field Registry entries LS-017 and
SEG-003 and Calculated Values LS-c002 and SEG-c002 — the Lots on Delay
spec has moved upstream to the BMD where it can be referenced by code.
No code changed; no test changed; no behavior change. Federation
decision log:
`~/Documents/GitHub/ehc-federation/decisions/phase-6-kill-local-dictionaries.md`.

Branch: `phase-6-kill-local-dictionaries`. Rollback tag: `pre-phase-6`.

---

## 2026-04-22 — Phase 4.5 (EHC Federation Cohesion Plan)

Added `ehc_contracts.metrics.lb_margin` — the shared Land Bank Margin
primitive, covering the two CashFlow-sum formulas that are genuinely
duplicated across emitters (Formula 1 — 9-col Rule 1; Formula 2 —
7-col per Jeff's A1 ruling for origination_detail). Three exports:

- `FLOW_COLS` — frozen tuple of 9 qs_CashFlow column names. The
  canonical Rule 1 definition (includes Plat_Fee, Cost_Hiatus, TrueUp).
- `LB_MARGIN_COLS` — frozen tuple of 7 column names. Excludes
  Plat_Fee and Cost_Hiatus per the origination_detail investment-case
  discipline. Preserves the auditor's existing ordering (Other_SU
  before TrueUp) to avoid churn on any list-equality surface.
- `lb_margin(rows, cols=FLOW_COLS) -> float` — sums specified columns
  across monthly cashflow rows. Accepts any Mapping (dict, Series).
  Empty rows return 0.0 (sum semantics, not None semantics — unlike
  IRR/MOIC). NaN/None/missing keys contribute 0 (defense in depth).

Lives alongside IRR/MOIC in `ehc_contracts/metrics/` as a sibling
module. The primary value is the canonical column constants — every
caller imports the same list from one place. Pandas-rich callers use
`df[list(FLOW_COLS)].sum().sum()`; dict-row callers use the function.

**Scope deliberately limited.** LB Margin has FIVE distinct formulas
across the federation; Phase 4.5 migrates only the two column-sum
formulas. The three hybrid formulas (Dashboard Investment Summary,
Dashboard Reforecast Margin, Reporting App per-project fund-to-date)
are intentionally distinct metrics that share a name. See the
federation decision memo at
`~/Documents/GitHub/ehc-federation/decisions/phase-4-5-lb-margin.md`
for the full five-way comparison.

Fixture coverage: 10 closed-form + 5 edge cases in
`tests/bmd_fixtures/lb_margin_cases.json`. The test_lb_margin.py
suite has 26 cases; full `ehc-contracts` suite: 143/143 green (+26
new LB Margin tests). Auditor parity: 7/7 green.

Numerical diff: **0 mismatches across 2,530 LB Margin rows** on the
2026-04-09 V3 workbook (4 funds × fund/segment/per-project/per-builder
× P/F × 9-col and 7-col variants) comparing three pre-migration
implementations (Dashboard local FLOW_COLS, Auditor 9-col, Auditor
7-col) against the new shared module at ±1e-6 absolute tolerance.
LB Margin is non-iterative arithmetic — byte-equality was the expected
outcome.

No R twin. LB Margin R-side uses Formula 5 (cumulative-through-per_end
hybrid in data_prep.R LOCKED) which is a different formula; Formula 1
does not exist R-side.

BACKLOG 4.1.1 step 1 closed: R-side `LB_Margin = "P"` override
hoisted out of the totals loop in emit_manifest.R to a file-scope
constant (`.DERIVED_TYPE_OVERRIDES`). Steps 2 and 3 remain open.

---

## 2026-04-22 — Phase 4.4 (EHC Federation Cohesion Plan)

Added `ehc_contracts.metrics.moic` — the shared Multiple on Invested
Capital implementation emitted as fund / active / closed / builder /
project MOICs across all three emitters. One function, no flags:

- `moic(cashflows)` → `float | None`. Returns
  `sum(c > 0) / abs(sum(c < 0))`, or `None` on empty input / division
  by zero / any NaN. Total-loss cashflows (positives=0 with negatives
  present) return `0.0` — a legitimate outcome, not a missing value.
- Lives alongside `irr_newton_raphson` in
  `ehc_contracts/metrics/irr.py`. The two metrics share the same
  monthly unleveraged cashflow shape and are reported together in
  every emitter — one module, one fixture-directory pair.

No caller-scoped flags. Unlike IRR's Option C policy flag, MOIC's
four pre-migration implementations (Dashboard / ProjFin / R
`safe_moic` / Auditor `moic_calc`) agreed on every edge case once
None↔NA is mapped. The shared function adopts that unanimous contract
directly. See the federation decision memo at
`~/Documents/GitHub/ehc-federation/decisions/phase-4-4-moic.md` for
the full comparison table.

Fixture coverage: 10 closed-form classified cases + 7 edge cases in
`tests/bmd_fixtures/moic_cases.json`. The `test_irr.py` suite gained
22 new cases, bringing the file total to 44 (22 IRR + 22 MOIC). Full
`ehc-contracts` suite: 117/117 green. Auditor parity: 6/6 green (the
auditor's own `moic_calc` at `recalculate_metrics.py:177` is the
independent second implementation verified against the same fixture).

R twin: added `moic(cashflows)` and `safe_moic(unlev_cashflows)` to
`ehc-board-reporting-app/Support/irr.R`; the legacy `safe_moic`
migrated out of `Support/theme.R` as a thin wrapper preserving the
NA-aware `na.rm = TRUE` semantics that `build_report_specs.R` (SACRED)
relies on. R test suite extended: 45/45 green.

Numerical diff: zero drift across 1,714 MOIC rows on the 2026-04-09
V3 workbook (730 EHF2 + 856 TPG AG 3 + 106 TPG AG SD + 22 TPG EHC E)
comparing all four pre-migration implementations against the new
shared module at ±1e-9 absolute tolerance. MOIC is non-iterative
arithmetic — byte-equality was the expected outcome.

---

## 2026-04-22 — Phase 4.3 (EHC Federation Cohesion Plan)

Added `ehc_contracts.metrics.irr` — the shared Newton-Raphson IRR
implementation emitted as fund / active / closed / builder / project
annualized IRRs across all three emitters. One function + one
exception + one constant:

- `irr_newton_raphson(cashflows, *, guess=0.01, max_iter=1000,
  tol=1e-8, dnpv_eps=1e-12, on_nonconvergence="best_estimate")` →
  `float | None`. Monthly iteration, annualized ×12. The
  `on_nonconvergence` flag is caller-scoped — `"best_estimate"` for
  Dashboard / ProjFin (return `rate × 12`), `"none"` for the Auditor
  (return `None`), `"raise"` for the R twin's legacy `stop()`
  semantics via `IRRNonConvergenceError`. Same Option-C precedent as
  Phase 4.2's TERM policy: the shared function takes no policy; the
  caller picks the behavior that preserves its published numbers.
- `IRRNonConvergenceError(RuntimeError)` — raised only when
  `on_nonconvergence="raise"`. The R twin's `safe_irr_custom`
  tryCatch converts it to `NA`.
- `VALID_NONCONVERGENCE_MODES` — frozenset of the three valid modes
  for caller validation.

Bridged to R via a twin at `ehc-board-reporting-app/Support/irr.R` —
same iteration, same edge-case semantics, same fixture. No
reticulate: the Shiny deploy has no existing Python runtime and
Newton-Raphson is a ~20-line algorithm that hasn't churned. See
`~/Documents/GitHub/ehc-federation/decisions/phase-4-3-irr.md` for
the full decision memo and surprises list.

Fixture: `tests/bmd_fixtures/irr_cases.json` — 9 closed-form
classified cases + 3 edge cases (mode-dependent) + 2 param-parity
cases proving the R-legacy `max_iter=100, tol=1e-6` parameters still
produce the same display value as the Python `max_iter=1000, tol=1e-8`
defaults. Tolerance **±1e-5 absolute** on the decimal-form annualized
IRR (±0.001 percentage points on the rendered percent) — tighter
than the BMD's ±0.01% display tolerance per Jeff's Phase 4.3
ratification.

Testing:

- `tests/test_irr.py`: 22/22 green. Full suite: 95/95 green.
- `ehc-board-reporting-app/tests/test_irr.R`: 23/23 green.
- `ehc-data-analysis/data_board_auditor/tests/test_auditor_bmd_parity.py`:
  5/5 green (now includes `irr_parity_with_bmd_fixtures`).
- Numerical diff at
  `ehc-federation/diffs/phase-4-3-irr.md`: **0 mismatches across
  1,714 IRR rows** on the 2026-04-09 V3 workbook (four funds × fund
  / scope / per-project / per-builder × P and F), compared against
  three pre-migration implementations (Dashboard pure-Python,
  ProjFin numpy, Reporting App R-legacy).

---

## 2026-04-22 — Phase 4.2 (EHC Federation Cohesion Plan)

Added `ehc_contracts.metrics.lots_on_delay` — the shared primitive for
the per-project delay count emitted on ProjFin's KPI tile and the
"behind on lot-type variance" set behind Dashboard's
`snapshot_delayed_takedowns`. Two pure functions + two constants:

- `compute_lot_variance(p_lot_sums, f_lot_sums)` → `(is_behind,
  abs_neg_variance)`. Pure-math primitive — no pandas. Callers build
  per-lot-type P and F aggregate dicts from whatever DataFrame shape
  they hold.
- `lots_on_delay_count(is_behind, abs_neg_variance, ph_lots)` → `int`.
  Three-rule count: Rule 1 (behind & ph_lots > 0 → ph_lots), Rule 2
  (behind & ph_lots == 0 → abs_neg_variance), Rule 3 (not behind → 0).
- Constants `LOT_TYPES = ("A", …, "G")` and `MNTH_LOT_COLS` — the
  canonical lot-type column names in `qs_CashFlow`.

Fixture: `tests/bmd_fixtures/lots_on_delay_cases.json` (14 variance
cases + 2 invalid-input cases covering negative variance and negative
ph_lots).

**No R side.** Reporting App has no Lots-on-Delay metric at any grain —
the closest R artifacts are per-month lot counts on plat/hiatus
reports, not a rule-based delay count. No R twin, no reticulate.

**TERM filtering is caller-scoped (Option C).** Each emitter chooses
its own TERM policy by which project IDs it feeds the functions. The
shared module takes no TERM parameter. Preserves ProjFin's "include
TERM on per-project tile" and Dashboard's "exclude TERM from fund-level
snapshot" without a policy baked into the primitive.

Diff report: `ehc-federation/diffs/phase-4-2-lots-on-delay.md` — 0
drift across 798 per-project values + 4 fund-level counts on the
2026-04-09 V3 workbook, actuals through 2026-03-01.

Federation decision log: `~/Documents/GitHub/ehc-federation/decisions/
phase-4-2-lots-on-delay.md`.

---

## 2026-04-22 — Phase 4.1 (EHC Federation Cohesion Plan)

Added `ehc_contracts.metrics.pf_routing` — the canonical classifier for
the `value_types` annotation emitters carry in every manifest. Two
functions:

- `classify_value_type(metric_name, *, overrides=None, default=None)` —
  returns one of `{"P", "F", "IGEN", "INVARIANT"}` with precedence
  `overrides[name]` → `^mnth_Prof_|^mnth_Pro_` → "P" / `^mnth_Act_` →
  "F" → `default` → `UnclassifiedMetricError`.
- `build_value_types_dict(names, *, overrides=None, default=None)` —
  bulk wrapper that collects every unclassified name into one error.

Fixture: `tests/bmd_fixtures/pf_routing_cases.json` (14 classified + 2
unclassified cases).

**R twin, not reticulate.** The R-side bridge is a pure-R twin at
`ehc-board-reporting-app/Support/pf_routing.R`, verified against the
same fixture JSON. Reticulate was the plan (see
`EHC_FEDERATION_COHESION_PLAN.md` Move 1) but deferred for 4.1 —
P/F routing is small rule-based logic, carrying a second 15-line R
implementation is cheaper than taking a runtime Python dependency for
the R deploy surface. The fixture is the shared spec; the Board
Auditor continues to carry its own independent implementation tested
against the same fixture. Reticulate remains the likely bridge for
heavier math (target: Phase 4.3 IRR). Full rationale in the federation
decision log at `~/Documents/GitHub/ehc-federation/decisions/phase-4-1-
pf-routing.md`.

Diff report: `ehc-federation/diffs/phase-4-1-pf-routing.md` — 0 drift
across 362 classified metrics.

Branch: `phase-4.1-pf-routing`. Rollback tag: `pre-phase-4.1`.

---

## 2026-04-22 — Phase 3.5 (EHC Federation Cohesion Plan)

Repo created. Shipped `ehc_contracts.metrics.recast.identify_recast_
projects(board)` as the first migrated metric. Python 3.9+ compatible
for local dev (Jeff's laptop); CI uses 3.11. 11 tests green (8 BMD
fixture cases + 3 sanity tests). Imported by
`ehc-board-project-financials/pipeline/compute.py`; the Board Auditor
keeps its own independent copy with a parity test.

Federation decision log: `ehc-federation/decisions/phase-3.5-recast-
proof.md`.

Branch: `phase-3.5-recast-proof`. Rollback tag: `pre-phase-3.5`.
