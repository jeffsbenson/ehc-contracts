# ehc-contracts — History

Dated entries for shared metrics, fixtures, and schemas. For current
rules and the package layout, read `README.md` and each module's
docstring. Entries in reverse chronological order.

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
