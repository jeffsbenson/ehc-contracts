# ehc-contracts — History

Dated entries for shared metrics, fixtures, and schemas. For current
rules and the package layout, read `README.md` and each module's
docstring. Entries in reverse chronological order.

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
