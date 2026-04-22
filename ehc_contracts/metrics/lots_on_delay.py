"""Lots-on-Delay metric — per-project count of lots flagged as delayed.

Historically implemented in three places:

  * Dashboard  — ``pipeline/compute.py`` — ``_proj_behind_ids_at(cf_f, cf_p,
    active_ids, date_end)``: returns the set of active project IDs whose
    cumulative F-type takedowns are behind the P-type schedule at
    ``date_end`` on any lot type A–G. Used by three different fund-level
    aggregations: ``snapshot_delayed_takedowns`` (project count, TERM
    excluded), ``lots_behind_plat_hiatus`` (Rule-1-only lot sum, TERM
    excluded), and the §4.9 trailing-6-month fees chart.
  * ProjFin    — ``pipeline/compute.py`` — ``_compute_lots_on_delay(pid, ...)``:
    returns a per-project int applying three rules (Rule 1 plat/hiatus,
    Rule 2 variance, Rule 3 zero). Rendered on the per-project KPI tile.
    Today's behavior iterates every non-recast project including TERM.
  * Reporting App — no equivalent metric. The R side emits per-month
    plat/hiatus fee reports but has no rule-based "delay count" concept.

The shared primitive every caller uses is *"is this project behind on
cumulative lot-type variance at a point in time?"* — a pure math rule
with no pandas dependency. That primitive, plus the three-rule per-project
count, lives here. DataFrame filtering (``Julian_Date <= per_end``, the
actuals-fallback when ``cf_f_valid`` is empty, the ``qs_Plat_Hiatus``
join) stays in the emitters.

**Auditor independence.** The Board Auditor does NOT import this module.
Its own independent "behind" set lives at
``ehc-data-analysis/data_board_auditor/scripts/recalculate_metrics.py``
(``compute_eligible_ids``). Both implementations are tested against the
same fixture file. If they disagree, the BMD is the tiebreaker.

**TERM filtering is caller-scoped.** The two emitters today apply
different TERM policies and both are considered correct for their
audience:

  * Dashboard's ``snapshot_delayed_takedowns`` excludes TERM projects
    (the fund-level "how many projects are delayed" count is about live
    pipeline).
  * ProjFin's ``lots_on_delay`` tile includes TERM projects (the
    per-project page still needs to surface a delay count for the
    builder that walked away).

The shared functions here intentionally take no TERM parameter — the
caller chooses which project IDs to feed in, and the choice is visible at
each call site.

Authoritative spec: EHC Business Math Dictionary (see ``ehc-data-analysis/
context/EHC_Business_Math_Dictionary.xlsx`` → "Lots on Delay Logic" sheet
of ``Project_Financials_Data_Dictionary.xlsx``). Fixture cases in
``tests/bmd_fixtures/lots_on_delay_cases.json``.
"""

from __future__ import annotations

from typing import Mapping


LOT_TYPES = ("A", "B", "C", "D", "E", "F", "G")
MNTH_LOT_COLS = tuple(f"mnth_{lt}_Lots" for lt in LOT_TYPES)


def compute_lot_variance(
    p_lot_sums: Mapping[str, float],
    f_lot_sums: Mapping[str, float],
) -> tuple[bool, float]:
    """Return ``(is_behind, abs_neg_variance)`` for one project.

    Given per-lot-type cumulative aggregates for P (proforma) and F
    (actuals/forecast) through some point in time, compute the
    lot-type-level variance and return whether the project is behind.

    The rule is **lot-type-level**, not total-level: a project is behind
    if ``F − P < 0`` on *any* lot type in the ``p_lot_sums`` mapping,
    even if positive variance on other lot types brings the total
    variance positive. ``abs_neg_variance`` is the sum of the absolute
    values of the negative deltas only — positive deltas (accelerated
    takedowns) are ignored.

    Parameters
    ----------
    p_lot_sums : Mapping[str, float]
        ``{lot_col: sum}`` for P-type cashflow rows filtered to the
        relevant period. Typically keyed by ``mnth_A_Lots`` …
        ``mnth_G_Lots`` (see ``MNTH_LOT_COLS``). Missing or ``None``
        values are treated as 0.
    f_lot_sums : Mapping[str, float]
        Same shape, F-type. Missing keys are treated as 0.

    Returns
    -------
    tuple[bool, float]
        ``(is_behind, abs_neg_variance)``. ``is_behind`` is True iff any
        lot type has a strictly negative delta. ``abs_neg_variance`` is
        the sum of ``|min(0, F - P)|`` across all lot types in
        ``p_lot_sums``.

    Notes
    -----
    Iteration is driven by the keys of ``p_lot_sums`` — callers should
    pass every lot type they care about in the P dict, even if the P
    sum is 0. This matches the emitters' current behavior of iterating
    the full ``MNTH_LOT_COLS`` tuple. ``f_lot_sums`` may have a subset
    or superset of those keys; missing F keys default to 0.
    """
    neg = 0.0
    for lot_col, p_raw in p_lot_sums.items():
        p_val = float(p_raw) if p_raw is not None else 0.0
        f_raw = f_lot_sums.get(lot_col, 0.0)
        f_val = float(f_raw) if f_raw is not None else 0.0
        delta = f_val - p_val
        if delta < 0:
            neg += -delta
    return (neg > 0, neg)


def lots_on_delay_count(
    is_behind: bool,
    abs_neg_variance: float,
    ph_lots: float,
) -> int:
    """Three-rule per-project Lots on Delay count.

    Rule 1 — behind AND ``ph_lots > 0``: return ``int(round(ph_lots))``.
    Rule 2 — behind AND ``ph_lots == 0``: return
    ``int(round(abs_neg_variance))``.
    Rule 3 — not behind: return 0.

    Parameters
    ----------
    is_behind : bool
        Output of :func:`compute_lot_variance` (first element).
    abs_neg_variance : float
        Output of :func:`compute_lot_variance` (second element). Must
        be ≥ 0. Ignored in Rule 1 and Rule 3 paths.
    ph_lots : float
        Sum of ``qs_Plat_Hiatus.Lots`` for this project in the current
        month (``actuals_thru_date`` ≤ ``Option_Date`` ≤ ``per_end``).
        Callers pass 0 or 0.0 when the project has no current-month
        plat/hiatus rows. Negative values raise ``ValueError`` — the
        source is a lot count and cannot be negative.

    Returns
    -------
    int
        ``int(round(...))`` so downstream integer comparisons match the
        rendered template output. ProjFin's template formats
        ``lots_on_delay`` as an integer with no decimals.

    Raises
    ------
    ValueError
        If ``abs_neg_variance`` or ``ph_lots`` is negative. Both are
        defined as non-negative in the BMD; a negative here is a bug
        upstream (usually a sign-convention error in the caller's
        aggregation).
    """
    if abs_neg_variance < 0:
        raise ValueError(
            f"abs_neg_variance must be non-negative; got {abs_neg_variance!r}. "
            f"This is a caller bug — compute_lot_variance never returns a "
            f"negative value."
        )
    if ph_lots < 0:
        raise ValueError(
            f"ph_lots must be non-negative; got {ph_lots!r}. "
            f"qs_Plat_Hiatus.Lots is a lot count and cannot be negative."
        )
    if is_behind and ph_lots > 0:
        return int(round(ph_lots))
    if is_behind:
        return int(round(abs_neg_variance))
    return 0
