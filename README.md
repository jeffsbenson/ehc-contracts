# ehc-contracts

> **What this is:** Shared metrics, JSON schemas, and validators for EHC Asset Management's three board-package emitters — Board Dashboard, Project Financials, and the Reporting App.
>
> **Auditor independence is non-negotiable.** The Board Package Auditor (in `ehc-data-analysis/data_board_auditor/`) does NOT import from this package and never will. It is a second, independent implementation of every BMD metric. Both implementations are tested against the same `tests/bmd_fixtures/` input→output pairs; neither depends on the other. If they diverge, one is wrong — that is the whole point.

---

## Install

Locally (editable, for development):

```
pip install -e ~/Documents/GitHub/ehc-contracts
```

From git (for CI):

```
pip install git+https://github.com/jeffsbenson/ehc-contracts.git@phase-3.5-recast-proof
```

## What's in the package

- `ehc_contracts.metrics` — BMD-derived metric implementations imported by the emitters (Dashboard, Project Financials) and wrapped in R for the Reporting App (Phase 4+).
- `ehc_contracts.schemas` — JSON Schema for manifest v1.0 and L3 sidecar v1.0 (Phase 4+).
- `ehc_contracts.validators` — `validate_manifest(payload)` and `validate_sidecar(payload)` (Phase 4+).
- `tests/bmd_fixtures/` — input→output pairs derived from the Business Math Dictionary. The independent test surface both this package AND the auditor are verified against.

## Shipped metrics

- **Phase 3.5 (2026-04-22).** `ehc_contracts.metrics.recast.identify_recast_projects(board)` — returns the set of project IDs flagged as recast in `dp_JSB_Board`. Migrated out of `ehc-board-project-financials/pipeline/compute.py`.
- **Phase 4.1 (2026-04-22).** `ehc_contracts.metrics.pf_routing` — `classify_value_type` and `build_value_types_dict` for P/F/IGEN/INVARIANT value-type classification. Bridged to R via a twin at `ehc-board-reporting-app/Support/pf_routing.R`.
- **Phase 4.2 (2026-04-22).** `ehc_contracts.metrics.lots_on_delay` — `compute_lot_variance` and `lots_on_delay_count` for the per-project 3-rule delay count. No R side — the metric does not exist in the Reporting App.
- **Phase 4.3 (2026-04-22).** `ehc_contracts.metrics.irr` — `irr_newton_raphson` (Newton-Raphson IRR on monthly cashflows, annualized ×12) with caller-scoped `on_nonconvergence` policy. Bridged to R via a twin at `ehc-board-reporting-app/Support/irr.R`.

Phase 4 sub-phases still to ship: MOIC (4.4), LB Margin (4.5).

The auditor keeps its own copy of every metric and is tested against the same `tests/bmd_fixtures/` pairs. If the auditor and the shared package disagree on a fixture case, the BMD is the tiebreaker.

## Context

See `~/Documents/GitHub/ehc-federation/CLAUDE.md` for the federation-wide index, `~/Documents/GitHub/ehc-federation/ARCHITECTURE.md` for where this package fits in the data flow, and `~/Documents/GitHub/EHC_FEDERATION_COHESION_PLAN.md` (Move 1) for the rationale.
