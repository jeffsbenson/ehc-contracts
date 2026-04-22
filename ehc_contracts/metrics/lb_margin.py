"""Land Bank Margin — the Rule 1 primitive.

**LB Margin has five formulas in the EHC federation.** Phase 4.5
(2026-04-22) ships the shared primitive for the first two — the
canonical "sum these CashFlow columns across these rows" family.
The other three are hybrid formulas (Dashboard Investment Summary,
Dashboard Reforecast Margin, Reporting App fund-to-date per-project
margin) that answer different business questions and are intentionally
preserved as distinct metrics in their emitters. See the federation
decision memo at
``~/Documents/GitHub/ehc-federation/decisions/phase-4-5-lb-margin.md``
for the full five-way comparison and why only Formulas 1-2 migrate.

**The two formulas this module covers.**

* **Formula 1 — 9-column (FLOW_COLS).** The canonical Rule 1
  definition per ``ehc-data-analysis/CLAUDE.md`` §4: LB Margin comes
  from ``qs_CashFlow`` and includes every revenue / cost / fee line
  (``Plat_Fee`` and ``Cost_Hiatus`` included). Used for fund-level,
  per-builder, per-state, per-region, closeout, and restatement LB
  Margin across every emitter that computes this metric.

* **Formula 2 — 7-column (LB_MARGIN_COLS).** A narrower set used by
  the ``origination_detail`` report (Reporting App). Per Jeff's A1
  ruling, Platform Fee and Cost Hiatus are excluded from that
  report's LB_Margin column — the investment-case pricing terms
  discipline predates the addition of those two fee lines to
  ``qs_CashFlow`` and the report preserves the original definition.
  The auditor calls out this divergence at
  ``recalculate_metrics.py:2496`` where the canonical comment lives.

**P vs F is orthogonal.** Whether the caller gets Proforma or Forecast
LB Margin depends entirely on whether they pass in P-type or F-type
cashflow rows — the formula itself doesn't know. In production:

* 9-column Formula 1 is called on BOTH P and F cashflows, producing
  side-by-side ``LB_Margin`` and ``LB_Margin_Actual`` outputs (or
  ``fund_p.*.lb_margin`` and ``fund_f.*.lb_margin`` in the auditor).
* 7-column Formula 2 is called only on P-type cashflows in current
  production code (origination_detail is a proforma-only report),
  but nothing about the math prevents a future F-type caller.

**What this module does NOT cover.**

* The Dashboard's ``_compute_investment_summary`` margin
  (``inv_{total,active,closed}_lb_margin``) which is a hybrid of
  P-type iGeneral totals plus P-type CashFlow fee supplements.
* The Dashboard's Reforecast Margin (``rfcst_{total,active,closed}_margin``)
  which is P-iGeneral costs/revenue plus F-CashFlow fees (a genuinely
  distinct quantity, not reducible to either column-sum formula).
* The Reporting App's per-project ``LB_Margin`` / ``LB_Margin_Actual``
  in ``data_prep.R`` which uses iGeneral full-project totals plus
  cumulative CashFlow fee-through-per_end — a fund-to-date view that
  the LOCKED ``data_prep.R`` file owns.

Each of those three hybrids answers a specific business question that
is not the same question this primitive answers. They intentionally
differ from Formulas 1-2 and from each other. Do not treat them as
copies of the same math.

**Auditor independence.** The Board Auditor does NOT import this
module. Its LB Margin computations at
``ehc-data-analysis/data_board_auditor/scripts/recalculate_metrics.py``
(``sum_metric_by_segment:201``, ``sum_metric_grouped:238``,
``recompute_ratios:309``, ``compute_report_row_values:2954``) are
independent second implementations, tested against the same fixture
via ``tests/test_auditor_bmd_parity.py``.

**Authoritative spec.** EHC Business Math Dictionary
(``ehc-data-analysis/context/EHC_Business_Math_Dictionary.xlsx``).
Fixture cases in ``tests/bmd_fixtures/lb_margin_cases.json``.
"""

from __future__ import annotations

import math
from typing import Iterable, Mapping


# ─── Canonical column sets ────────────────────────────────────────────
# Importers can use these constants directly with pandas operations
# (e.g. ``cf_seg[FLOW_COLS].sum().sum()``) without calling the function,
# which keeps the primitive useful in vectorized contexts where looping
# over rows would be wasteful. That's the main value the shared module
# provides — a single canonical list of columns that every caller
# imports instead of redeclaring locally.

FLOW_COLS: tuple[str, ...] = (
    "mnth_Gross_Revenue",
    "mnth_Cost_Land",
    "mnth_Cost_Site",
    "mnth_Cost_MUD",
    "mnth_Cost_Carry",
    "mnth_Plat_Fee",
    "mnth_Cost_Hiatus",
    "mnth_TrueUp",
    "mnth_Other_SU",
)
"""Nine-column canonical LB Margin from qs_CashFlow.

Includes Platform Fee, Cost Hiatus, and True-Up — the full Rule 1
definition. This is the default for fund-level, per-segment,
per-builder, per-state, per-region, and closeout LB Margin across
every emitter that computes this metric.
"""


LB_MARGIN_COLS: tuple[str, ...] = (
    "mnth_Gross_Revenue",
    "mnth_Cost_Land",
    "mnth_Cost_Site",
    "mnth_Cost_MUD",
    "mnth_Cost_Carry",
    "mnth_Other_SU",
    "mnth_TrueUp",
)
# Note: Other_SU precedes TrueUp here, mirroring the auditor's
# recalculate_metrics.py:48 ordering. FLOW_COLS has TrueUp before
# Other_SU. Ordering does not affect the sum; preserving the auditor's
# existing order avoids downstream churn on any list-equality check.
"""Seven-column LB Margin — excludes Platform Fee and Cost Hiatus.

Used only by the ``origination_detail`` report in the Reporting App,
per Jeff's A1 ruling that investment-case pricing terms exclude those
two fee lines from the per-project margin column. The auditor's
independent implementation at
``recalculate_metrics.py::compute_report_row_values`` (line 2954)
uses this column set.
"""


# ─── The primitive ────────────────────────────────────────────────────


def lb_margin(
    rows: Iterable[Mapping[str, object]],
    cols: Iterable[str] = FLOW_COLS,
) -> float:
    """Sum specified columns across monthly cashflow rows.

    ``LB Margin = sum(row[col] for row in rows for col in cols)``.

    Parameters
    ----------
    rows : iterable of mapping
        Each row is a dict-like record (``dict``, ``pandas.Series``,
        any ``Mapping``) keyed by the column names in ``cols``.
        Missing keys and ``None`` values contribute 0. ``NaN`` values
        contribute 0 (defense in depth — production callers
        pre-filter).
    cols : iterable of str, default ``FLOW_COLS``
        Which columns to sum. Pass :data:`FLOW_COLS` (9-col, default)
        for the canonical Rule 1 formula; pass :data:`LB_MARGIN_COLS`
        (7-col) for the origination_detail variant.

    Returns
    -------
    float
        Total LB Margin as a Python float. Empty ``rows`` returns
        ``0.0`` — sum semantics, not None semantics. A caller that
        needs to distinguish "no projects" from "zero margin" should
        guard on ``len(rows)`` before calling.

    Notes
    -----
    **Pandas is often faster.** This function exists to codify the
    column list and the sign/NaN contract. In pandas contexts, the
    equivalent one-liner ``df[list(FLOW_COLS)].sum().sum()`` is
    idiomatic and typically faster — just import :data:`FLOW_COLS` or
    :data:`LB_MARGIN_COLS` from this module instead of redefining the
    column list locally. That gives you the canonical definition
    without paying a row-iteration cost.

    **Sign conventions.** Cashflow revenue entries are positive;
    cashflow cost entries are negative. The sum is therefore
    (revenue + negative costs + fee lines) and represents net margin
    with the correct sign out of the box.

    **Empty-row semantics.** Unlike IRR and MOIC, which return
    ``None`` on empty input because a ratio is undefined, LB Margin
    returns ``0.0`` — summing an empty collection of non-negative
    widths is mathematically 0, and downstream "no projects in this
    segment" rendering handles the 0.0 correctly. Callers that need
    blank/dash semantics can check for empty themselves and skip the
    call.
    """
    cols_list = list(cols)
    total = 0.0
    for row in rows:
        for col in cols_list:
            v = row.get(col) if hasattr(row, "get") else row[col]
            if v is None:
                continue
            try:
                f = float(v)
            except (TypeError, ValueError):
                continue
            if math.isnan(f):
                continue
            total += f
    return total
