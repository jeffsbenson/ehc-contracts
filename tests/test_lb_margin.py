"""Tests for ``ehc_contracts.metrics.lb_margin``.

Fixture-driven. The Board Auditor's independent replica at
``ehc-data-analysis/data_board_auditor/tests/test_auditor_bmd_parity.py``
is verified against the same fixture file.

Phase 4.5 scope: the shared primitive handles Formula 1 (9-col
FLOW_COLS) and Formula 2 (7-col LB_MARGIN_COLS). Three additional
formulas in the federation (Dashboard Investment Summary, Dashboard
Reforecast Margin, Reporting App fund-to-date per-project) are
intentionally distinct metrics and are not covered by this module.
See ``~/Documents/GitHub/ehc-federation/decisions/phase-4-5-lb-margin.md``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ehc_contracts.metrics.lb_margin import (
    FLOW_COLS,
    LB_MARGIN_COLS,
    lb_margin,
)


FIXTURE_PATH = Path(__file__).parent / "bmd_fixtures" / "lb_margin_cases.json"


def _load_fixture():
    with open(FIXTURE_PATH) as f:
        return json.load(f)


_FIXTURE = _load_fixture()
_TOL = _FIXTURE["tolerance"]


def _resolve_cols(cols_name):
    """Fixture cases name the column set symbolically — resolve to the
    actual constant imported from the shared module."""
    if cols_name == "FLOW_COLS":
        return FLOW_COLS
    if cols_name == "LB_MARGIN_COLS":
        return LB_MARGIN_COLS
    raise ValueError(f"Unknown cols name in fixture: {cols_name!r}")


def _coerce_rows(rows):
    """JSON has no native NaN; fixture encodes NaN as the string 'NaN'."""
    out = []
    for r in rows:
        coerced = {}
        for k, v in r.items():
            if isinstance(v, str) and v.lower() == "nan":
                coerced[k] = float("nan")
            else:
                coerced[k] = v
        out.append(coerced)
    return out


# ── Column-set identity invariants ──────────────────────────────────────
def test_flow_cols_has_9_entries():
    assert len(FLOW_COLS) == 9


def test_lb_margin_cols_has_7_entries():
    assert len(LB_MARGIN_COLS) == 7


def test_lb_margin_cols_excludes_plat_and_hiatus():
    """Jeff's A1 ruling — Plat_Fee and Cost_Hiatus are specifically
    the two columns that differ between the 9-col and 7-col sets."""
    assert "mnth_Plat_Fee" not in LB_MARGIN_COLS
    assert "mnth_Cost_Hiatus" not in LB_MARGIN_COLS
    assert "mnth_Plat_Fee" in FLOW_COLS
    assert "mnth_Cost_Hiatus" in FLOW_COLS


def test_flow_cols_minus_excluded_equals_lb_margin_cols_as_set():
    """The 7-col set is exactly the 9-col set minus Plat_Fee and Hiatus
    (by set equality). Ordering differs — the auditor's historical
    ordering (Other_SU before TrueUp in LB_MARGIN_COLS; TrueUp before
    Other_SU in FLOW_COLS) is preserved in both constants. Ordering
    does not affect the sum."""
    excluded = {"mnth_Plat_Fee", "mnth_Cost_Hiatus"}
    derived = {c for c in FLOW_COLS if c not in excluded}
    assert derived == set(LB_MARGIN_COLS)


def test_both_sets_agree_on_declared_columns():
    """The fixture's declared flow_cols and lb_margin_cols must match
    the constants exported from the shared module — prevents drift
    between the JSON spec and the Python code."""
    assert tuple(_FIXTURE["flow_cols"]) == FLOW_COLS
    assert tuple(_FIXTURE["lb_margin_cols"]) == LB_MARGIN_COLS


# ── Classified closed-form cases ────────────────────────────────────────
@pytest.mark.parametrize("case", _FIXTURE["cases"], ids=lambda c: c["name"])
def test_closed_form_case(case):
    rows = _coerce_rows(case["rows"])
    cols = _resolve_cols(case["cols"])
    got = lb_margin(rows, cols=cols)
    expected = case["expected_margin"]
    assert abs(got - expected) <= _TOL, (
        f"Case '{case['name']}': got {got!r}, expected {expected!r}, "
        f"delta {abs(got - expected)!r} exceeds tolerance {_TOL!r}."
    )


# ── Edge cases ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("case", _FIXTURE["edge_cases"], ids=lambda c: c["name"])
def test_edge_case(case):
    rows = _coerce_rows(case["rows"])
    cols = _resolve_cols(case["cols"])
    got = lb_margin(rows, cols=cols)
    expected = case["expected_margin"]
    assert got == expected, (
        f"Case '{case['name']}': got {got!r}, expected {expected!r}."
    )


# ── Return-type invariants ──────────────────────────────────────────────
def test_returns_float_on_nonempty():
    row = {c: 1.0 for c in FLOW_COLS}
    assert type(lb_margin([row])) is float


def test_returns_float_zero_on_empty():
    """Unlike IRR/MOIC which return None on empty, LB Margin is a sum
    and empty-sum is exactly 0.0. Rendering layer handles this."""
    result = lb_margin([])
    assert result == 0.0
    assert type(result) is float


def test_accepts_non_dict_mapping():
    """Should accept any Mapping, not just dict. Simulates pandas Series."""
    class DictLike:
        def __init__(self, data):
            self._data = data
        def get(self, key, default=None):
            return self._data.get(key, default)

    row = DictLike({"mnth_Gross_Revenue": 500, "mnth_Cost_Land": -200})
    # Other columns missing — treated as 0. Margin = 500 - 200 = 300.
    assert lb_margin([row]) == 300.0


# ── Default column parameter ────────────────────────────────────────────
def test_default_cols_is_flow_cols():
    """Omitting `cols` should use FLOW_COLS (9-col, canonical Rule 1)."""
    row = {c: 0 for c in FLOW_COLS}
    row["mnth_Plat_Fee"] = 100  # only nonzero in Plat_Fee
    # 9-col includes Plat_Fee → 100. 7-col excludes → 0.
    assert lb_margin([row]) == 100.0  # default (FLOW_COLS)
    assert lb_margin([row], cols=LB_MARGIN_COLS) == 0.0  # explicit 7-col


# ── Pandas-like usage pattern (no pandas dep, simulated) ────────────────
def test_constants_usable_as_list_in_pandas_idiom():
    """The canonical pandas one-liner is ``df[list(FLOW_COLS)].sum().sum()``.
    This test just confirms FLOW_COLS converts cleanly to a list — the
    typical shape a pandas column selector expects."""
    col_list = list(FLOW_COLS)
    assert col_list == [
        "mnth_Gross_Revenue", "mnth_Cost_Land", "mnth_Cost_Site",
        "mnth_Cost_MUD", "mnth_Cost_Carry", "mnth_Plat_Fee",
        "mnth_Cost_Hiatus", "mnth_TrueUp", "mnth_Other_SU",
    ]


# ── Sign discipline ─────────────────────────────────────────────────────
def test_negative_costs_reduce_margin():
    """Cost columns carry negative values in CashFlow. Margin = revenue
    + costs (where costs are already negative). This test pins the sign
    contract so a caller that mistakenly pre-abs()s costs will see a
    clear failure."""
    row = {
        "mnth_Gross_Revenue": 1000,
        "mnth_Cost_Land": -400,
        "mnth_Cost_Site": -100,
        "mnth_Cost_MUD": 0, "mnth_Cost_Carry": 0,
        "mnth_Plat_Fee": 0, "mnth_Cost_Hiatus": 0,
        "mnth_TrueUp": 0, "mnth_Other_SU": 0,
    }
    # Revenue 1000 + (costs summing to -500) = 500
    assert lb_margin([row]) == 500.0
