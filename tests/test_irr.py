"""Tests for ``ehc_contracts.metrics.irr``.

Fixture-driven. The Reporting App's R twin at
``ehc-board-reporting-app/Support/irr.R`` and the Board Auditor's
independent replica at
``ehc-data-analysis/data_board_auditor/tests/test_auditor_bmd_parity.py``
are both verified against the same fixture file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ehc_contracts.metrics.irr import (
    IRRNonConvergenceError,
    VALID_NONCONVERGENCE_MODES,
    irr_newton_raphson,
)


FIXTURE_PATH = Path(__file__).parent / "bmd_fixtures" / "irr_cases.json"


def _load_fixture():
    with open(FIXTURE_PATH) as f:
        return json.load(f)


_FIXTURE = _load_fixture()
_TOL = _FIXTURE["tolerance"]


# ── Closed-form classified cases ────────────────────────────────────────
@pytest.mark.parametrize("case", _FIXTURE["cases"], ids=lambda c: c["name"])
def test_closed_form_case(case):
    """Each case specifies cashflows and the expected annualized IRR.
    Python defaults (max_iter=1000, tol=1e-8, best_estimate) must produce
    a value within ±1e-5 absolute of the expected (±0.001 percentage
    points on the rendered percent)."""
    got = irr_newton_raphson(case["cashflows"])
    expected = case["expected_annualized_irr"]
    assert got is not None, (
        f"Case '{case['name']}': got None, expected {expected!r}."
    )
    assert abs(got - expected) <= _TOL, (
        f"Case '{case['name']}': got {got!r}, expected {expected!r}, "
        f"delta {abs(got - expected)!r} exceeds tolerance {_TOL!r}."
    )


# ── Edge cases — assert behavior under each mode ────────────────────────
def test_empty_list_returns_none_always():
    for mode in VALID_NONCONVERGENCE_MODES:
        assert irr_newton_raphson([], on_nonconvergence=mode) is None, (
            f"Empty cashflows must return None under on_nonconvergence={mode!r}."
        )


def test_single_cashflow_returns_none_always():
    for mode in VALID_NONCONVERGENCE_MODES:
        assert irr_newton_raphson([-100], on_nonconvergence=mode) is None, (
            f"Single cashflow must return None under on_nonconvergence={mode!r}."
        )


def test_all_zeros_best_estimate_returns_annualized_guess():
    """All-zero cashflow hits the dnpv_eps path immediately. 'best_estimate'
    mode returns rate × 12 at the initial guess (0.01 × 12 = 0.12)."""
    result = irr_newton_raphson([0, 0, 0], on_nonconvergence="best_estimate")
    assert result == pytest.approx(0.12)


def test_all_zeros_none_returns_none():
    result = irr_newton_raphson([0, 0, 0], on_nonconvergence="none")
    assert result is None


def test_all_zeros_raise_raises():
    with pytest.raises(IRRNonConvergenceError):
        irr_newton_raphson([0, 0, 0], on_nonconvergence="raise")


# ── Parameter parity — Python vs R twin ─────────────────────────────────
@pytest.mark.parametrize(
    "case", _FIXTURE["param_parity_cases"], ids=lambda c: c["name"]
)
def test_python_r_parameter_parity(case):
    """Same cashflow, Python defaults vs R-twin defaults. Must agree
    within ±1e-5 absolute — proves the R twin's looser tolerances do not
    drift at display precision for realistic inputs."""
    py = irr_newton_raphson(case["cashflows"], **case["python_params"])
    r = irr_newton_raphson(case["cashflows"], **case["r_params"])
    assert py is not None and r is not None
    assert abs(py - r) <= _TOL, (
        f"Case '{case['name']}': Python params gave {py!r}, R params "
        f"gave {r!r}, delta {abs(py - r)!r} exceeds tolerance {_TOL!r}."
    )


# ── Invalid on_nonconvergence mode ──────────────────────────────────────
def test_invalid_mode_raises_value_error():
    with pytest.raises(ValueError) as excinfo:
        irr_newton_raphson([-100, 100], on_nonconvergence="nope")
    assert "on_nonconvergence" in str(excinfo.value)


# ── Type / shape checks ─────────────────────────────────────────────────
def test_accepts_iterable_not_just_list():
    """The function accepts any iterable — tuple, numpy array, generator
    expression — as long as it materializes into numeric cashflows."""
    result_list = irr_newton_raphson([-100, 110])
    result_tuple = irr_newton_raphson((-100, 110))
    result_gen = irr_newton_raphson(x for x in [-100, 110])
    assert result_list == pytest.approx(result_tuple)
    assert result_list == pytest.approx(result_gen)


def test_converged_returns_float():
    result = irr_newton_raphson([-100, 110])
    assert type(result) is float


def test_empty_returns_none_type():
    assert irr_newton_raphson([]) is None


# ── Annualization invariant ─────────────────────────────────────────────
def test_annualization_factor_is_exactly_12():
    """Monthly rate ×12. For -100/+101 the monthly rate is exactly 0.01
    and the annualized must be exactly 0.12 — proves we multiply by 12,
    not 12.0 with a rounding quirk or (1+r)^12 - 1 compounding."""
    result = irr_newton_raphson([-100, 101])
    assert result == pytest.approx(0.12, abs=1e-10)


# ── NaN/Inf guard ───────────────────────────────────────────────────────
def test_nan_in_cashflow_propagates_to_none():
    """A NaN cashflow produces a NaN new_rate; the guard returns None.
    This path is not exercised in production (callers pre-filter) but
    the guard must hold as a defense-in-depth measure."""
    result = irr_newton_raphson([-100, float("nan"), 110])
    assert result is None
