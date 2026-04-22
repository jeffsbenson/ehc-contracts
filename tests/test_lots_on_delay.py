"""Tests for ``ehc_contracts.metrics.lots_on_delay``.

Fixture-driven. The Board Auditor's independent implementation lives in
``ehc-data-analysis/data_board_auditor/tests/test_auditor_bmd_parity.py``
(a standalone replica of ``compute_lot_variance`` + ``lots_on_delay_count``)
and is verified against this same fixture file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ehc_contracts.metrics.lots_on_delay import (
    LOT_TYPES,
    MNTH_LOT_COLS,
    compute_lot_variance,
    lots_on_delay_count,
)


FIXTURE_PATH = Path(__file__).parent / "bmd_fixtures" / "lots_on_delay_cases.json"


def _load_fixture():
    with open(FIXTURE_PATH) as f:
        return json.load(f)


_FIXTURE = _load_fixture()


@pytest.mark.parametrize("case", _FIXTURE["cases"], ids=lambda c: c["name"])
def test_compute_lot_variance_case(case):
    is_behind, abs_neg = compute_lot_variance(
        case["p_lot_sums"], case["f_lot_sums"]
    )
    assert is_behind == case["expected_is_behind"], (
        f"Case '{case['name']}': is_behind expected "
        f"{case['expected_is_behind']!r}, got {is_behind!r}."
    )
    assert abs_neg == pytest.approx(case["expected_abs_neg_variance"]), (
        f"Case '{case['name']}': abs_neg_variance expected "
        f"{case['expected_abs_neg_variance']!r}, got {abs_neg!r}."
    )


@pytest.mark.parametrize("case", _FIXTURE["cases"], ids=lambda c: c["name"])
def test_lots_on_delay_count_case(case):
    is_behind, abs_neg = compute_lot_variance(
        case["p_lot_sums"], case["f_lot_sums"]
    )
    result = lots_on_delay_count(is_behind, abs_neg, case["ph_lots"])
    assert result == case["expected_lots_on_delay"], (
        f"Case '{case['name']}': lots_on_delay expected "
        f"{case['expected_lots_on_delay']!r}, got {result!r}."
    )


@pytest.mark.parametrize(
    "case", _FIXTURE["invalid_cases"], ids=lambda c: c["name"]
)
def test_invalid_input_raises(case):
    exc_name = case["expected_exception"]
    exc_cls = {"ValueError": ValueError}[exc_name]
    with pytest.raises(exc_cls):
        lots_on_delay_count(
            case["is_behind"], case["abs_neg_variance"], case["ph_lots"]
        )


def test_lot_types_constant():
    assert LOT_TYPES == ("A", "B", "C", "D", "E", "F", "G")


def test_mnth_lot_cols_constant():
    assert MNTH_LOT_COLS == (
        "mnth_A_Lots", "mnth_B_Lots", "mnth_C_Lots", "mnth_D_Lots",
        "mnth_E_Lots", "mnth_F_Lots", "mnth_G_Lots",
    )


def test_compute_lot_variance_returns_plain_tuple():
    out = compute_lot_variance({"mnth_A_Lots": 1}, {"mnth_A_Lots": 1})
    assert type(out) is tuple
    assert len(out) == 2


def test_lots_on_delay_count_returns_int():
    """int(round(...)) at every return path — downstream template renders
    as an integer, so a float leak would format as '5.0' instead of '5'."""
    assert type(lots_on_delay_count(False, 0.0, 0.0)) is int
    assert type(lots_on_delay_count(True, 3.0, 0.0)) is int
    assert type(lots_on_delay_count(True, 3.0, 2.0)) is int


def test_empty_dicts_not_behind():
    """Calling with empty dicts must not raise — matches the emitter
    edge case where a project has no cashflow rows at all."""
    is_behind, neg = compute_lot_variance({}, {})
    assert is_behind is False
    assert neg == 0.0


def test_f_sums_superset_of_p_sums_ignored():
    """If F has lot types that P doesn't, those extras don't contribute
    to is_behind — iteration is driven by P keys only. This matches the
    emitter convention of passing the canonical MNTH_LOT_COLS tuple as
    P keys."""
    is_behind, neg = compute_lot_variance(
        {"mnth_A_Lots": 5},
        {"mnth_A_Lots": 5, "mnth_Z_Lots": -999},
    )
    assert is_behind is False
    assert neg == 0.0
