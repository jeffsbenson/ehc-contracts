"""Internal Rate of Return and Multiple on Invested Capital.

IRR is Newton-Raphson on monthly cashflows, annualized ×12 (see
:func:`irr_newton_raphson`). MOIC is sum(positive flows) / abs(sum(
negative flows)) on the same cashflow shape (see :func:`moic`). Both
metrics operate on the unleveraged monthly cashflow vector and are
used together throughout the board package — the Project Financials
page header shows both P and F IRR plus both P and F MOIC; the
Reporting App's comp_cflow headers do the same.

Historically implemented in four places with subtle differences:

  * Dashboard  — ``pipeline/irr.py`` — pure Python ``math``, returns ``rate×12``
    (best estimate) on non-convergence, ``None`` on NaN/Inf, ``None`` on
    empty/len<2. MOIC returns ``None`` on empty, all-zero, or when
    ``sum(negatives) == 0``.
  * ProjFin    — ``pipeline/irr.py`` — numpy vectorized, identical return
    semantics to Dashboard for both IRR and MOIC.
  * Reporting App — ``Support/theme.R`` (IRR) / ``Support/irr.R`` (post
    Phase 4.3) — ``irr_custom`` with ``max_iter=100, tol=1e-6``,
    ``stop()`` on non-convergence or near-zero derivative. ``safe_moic``
    returns ``NA`` on empty, all-NA, or when ``sum(negatives) == 0``.
    Phase 4.4 moved ``safe_moic`` out of ``theme.R`` into ``Support/
    irr.R``.
  * Auditor    — ``recalculate_metrics.py::irr_newton`` (IRR) /
    ``moic_calc`` (MOIC primitive, at line 177). The auditor's MOIC has
    no explicit empty-guard; every call site aggregates to monthly
    totals first (``fund_irr_moic``, ``fund_moic``) and pre-filters the
    empty case.

All four IRR implementations compute the same math: Newton-Raphson on
the monthly NPV, annualized by multiplying the converged monthly rate
by 12. Every difference is in *how they handle edge cases*, not in the
core iteration. All four MOIC implementations compute the same math:
``sum(c > 0) / abs(sum(c < 0))``. Differences are limited to
empty/None/NA handling and NaN tolerance.

IRR exposes edge-case behavior via **caller-scoped flags**
(:data:`VALID_NONCONVERGENCE_MODES`); MOIC has no flags — the math is
non-iterative arithmetic with no mode choices. See the Phase 4.2
"Option C" precedent: the shared primitive takes no policy unless the
callers actually disagree on policy.

**Auditor independence.** The Board Auditor does NOT import this module.
Its ``irr_newton`` at ``ehc-data-analysis/data_board_auditor/scripts/
recalculate_metrics.py:161`` and ``moic_calc`` at the same file line
177 are second, independent implementations. Both are tested against
the same fixture files. If they disagree on a fixture case, the BMD is
the tiebreaker.

**R twin.** The Reporting App calls R twins at ``ehc-board-reporting-
app/Support/irr.R`` for both IRR (:func:`irr_newton_raphson`) and MOIC
(:func:`moic`) that mirror this module's behavior exactly and are
verified against the same fixture files. No reticulate dependency.
See the Phase 4.1 decision memo for the rationale on keeping rule-based
bridges as R twins; Phase 4.3 (IRR) and Phase 4.4 (MOIC) apply the same
pattern because (a) the functions are small, (b) the algorithms do not
churn, and (c) adding reticulate to the Shiny deploy surface has
nontrivial operational cost.

**Authoritative spec.** EHC Business Math Dictionary (``ehc-data-analysis/
context/EHC_Business_Math_Dictionary.xlsx``). Fixture cases in
``tests/bmd_fixtures/irr_cases.json`` and ``tests/bmd_fixtures/
moic_cases.json``. IRR tolerance for cross-implementation parity:
**±0.001 percentage points** on the annualized result (``1e-5``
absolute on the decimal-form IRR). MOIC tolerance: **±1e-9 absolute**
on the ratio — MOIC is non-iterative so the only source of
cross-implementation drift is float-summation-order jitter between
pure-Python and numpy paths.
"""

from __future__ import annotations

import math
from typing import Iterable


VALID_NONCONVERGENCE_MODES = frozenset({"best_estimate", "none", "raise"})


class IRRNonConvergenceError(RuntimeError):
    """Raised when ``on_nonconvergence="raise"`` and Newton-Raphson fails
    to converge within ``max_iter`` iterations or hits a near-zero
    derivative. The R twin's ``stop()`` semantics map to this exception
    via ``safe_irr_custom``'s tryCatch wrapper."""


def irr_newton_raphson(
    cashflows: Iterable[float],
    *,
    guess: float = 0.01,
    max_iter: int = 1000,
    tol: float = 1e-8,
    dnpv_eps: float = 1e-12,
    on_nonconvergence: str = "best_estimate",
) -> float | None:
    """Monthly IRR via Newton-Raphson, annualized ×12.

    Parameters
    ----------
    cashflows : iterable of float
        Monthly unleveraged cashflow values. Index 0 is period 0 (the
        origin, not discounted); index 1 is period 1, etc. The function
        materializes the iterable once into a list.
    guess : float, default 0.01
        Initial monthly rate. ``0.01`` (~12% annualized) matches every
        production caller and is the only value that has been verified
        to converge on the full EHC fund set.
    max_iter : int, default 1000
        Maximum Newton-Raphson iterations. Dashboard / ProjFin / Auditor
        default. The R twin passes ``max_iter=100`` (its legacy default).
        Newton-Raphson converges quadratically on well-behaved cashflows;
        past ~20 iterations you are in a pathological case.
    tol : float, default 1e-8
        Convergence threshold on ``|new_rate − rate|``. Dashboard /
        ProjFin / Auditor default. The R twin passes ``tol=1e-6`` (its
        legacy default). Both are well below the display precision of
        a 2-decimal percent (1e-4), so the choice between them is
        visible only in pathological cases.
    dnpv_eps : float, default 1e-12
        If ``|dNPV/drate|`` falls below this, the iteration cannot make
        further progress without dividing by a near-zero. Behavior at
        this point is controlled by ``on_nonconvergence`` — see below.
    on_nonconvergence : {"best_estimate", "none", "raise"}, default "best_estimate"
        What to do when Newton-Raphson cannot return a converged value
        (either ``max_iter`` exhausted or ``|dNPV|`` fell below
        ``dnpv_eps``):

        * ``"best_estimate"`` — return ``rate × 12`` (Dashboard, ProjFin).
          The current best guess, annualized. Use when the caller would
          rather display a near-converged value than blank the cell.
        * ``"none"`` — return ``None`` (Auditor). Use when the caller's
          downstream logic (e.g., empty-set blank/dash rendering)
          expects ``None`` for "could not compute."
        * ``"raise"`` — raise :class:`IRRNonConvergenceError`. Matches
          the R twin's ``stop()`` semantics; caller wraps with the
          equivalent of R's ``tryCatch``.

    Returns
    -------
    float or None
        Annualized IRR (``monthly_rate × 12``), or ``None`` when the
        input is invalid (empty or length < 2) or when
        ``on_nonconvergence="none"`` and convergence failed, or when
        an intermediate rate evaluates to NaN/Inf.

    Raises
    ------
    IRRNonConvergenceError
        Only when ``on_nonconvergence="raise"`` and Newton-Raphson
        fails to converge within ``max_iter`` iterations or hits a
        near-zero derivative.
    ValueError
        If ``on_nonconvergence`` is not one of the three valid modes.

    Notes
    -----
    Empty and length-<1 cashflow inputs always return ``None`` regardless
    of ``on_nonconvergence``; a single cashflow cannot produce an IRR
    because IRR requires at least one inflow and one outflow across
    periods. NaN/Inf in an intermediate ``new_rate`` (can occur on
    degenerate cashflows where the quadratic approximation overshoots
    into a pole) always returns ``None`` to match Dashboard/ProjFin
    NaN/Inf-guard behavior; the auditor and R twin never exercised this
    path because their inputs are pre-filtered, and ``None`` is the
    safest cross-caller behavior.
    """
    if on_nonconvergence not in VALID_NONCONVERGENCE_MODES:
        raise ValueError(
            f"on_nonconvergence must be one of "
            f"{sorted(VALID_NONCONVERGENCE_MODES)}; got {on_nonconvergence!r}."
        )

    cf = list(cashflows)
    if len(cf) < 2:
        return None

    rate = float(guess)
    for _ in range(max_iter):
        npv = 0.0
        dnpv = 0.0
        for t, c in enumerate(cf):
            disc = (1.0 + rate) ** t
            npv += c / disc
            if t > 0:
                dnpv += -t * c / ((1.0 + rate) ** (t + 1))

        if abs(dnpv) < dnpv_eps:
            return _handle_nonconvergence(rate, on_nonconvergence)

        new_rate = rate - npv / dnpv
        if math.isnan(new_rate) or math.isinf(new_rate):
            return None
        if abs(new_rate - rate) < tol:
            return new_rate * 12
        rate = new_rate

    return _handle_nonconvergence(rate, on_nonconvergence)


def _handle_nonconvergence(rate: float, mode: str) -> float | None:
    if mode == "best_estimate":
        return rate * 12
    if mode == "none":
        return None
    raise IRRNonConvergenceError(
        f"IRR did not converge; last monthly rate estimate = {rate!r}"
    )


def moic(cashflows: Iterable[float]) -> float | None:
    """Multiple on Invested Capital.

    ``MOIC = sum(c > 0) / abs(sum(c < 0))`` on the monthly unleveraged
    cashflow vector. Non-iterative: one pass to split, one division.

    Parameters
    ----------
    cashflows : iterable of float
        Monthly unleveraged cashflow values. The function materializes
        the iterable once into a list. Period indexing is irrelevant
        to MOIC — only the sign of each element matters.

    Returns
    -------
    float or None
        The ratio ``sum(positives) / abs(sum(negatives))``, or ``None``
        when the input is empty, when any cashflow is NaN, or when
        ``sum(negatives) == 0`` (no invested capital → division by
        zero). An all-negative input with zero positives returns
        ``0.0`` — a legitimate total-loss MOIC, not a missing value.

    Notes
    -----
    **Caller-agreed semantics.** Every production caller — Dashboard,
    ProjFin, the Reporting App's ``safe_moic``, the auditor's
    ``fund_irr_moic`` / ``fund_moic`` — aggregates to fund/project
    monthly totals before calling MOIC. The function itself is not
    aware of projects, funds, or segments. Pre-aggregation is the
    caller's responsibility.

    **Empty and None handling.** An empty cashflow list returns
    ``None`` (not ``0.0``) — downstream rendering treats ``None`` /
    ``NA`` as blank/dash, whereas ``0.0`` would falsely imply a real
    total-loss outcome. This matches the empty-set semantics used for
    IRR and documented in the auditor's Session Q HANDOFF.

    **NaN propagation.** A NaN cashflow produces a NaN sum; the
    function detects this and returns ``None``. Production callers
    pre-filter NaN values via pandas / numpy — this guard is
    defense-in-depth parity with :func:`irr_newton_raphson`'s NaN/Inf
    handling.

    **Auditor independence.** The Board Auditor's ``moic_calc`` at
    ``ehc-data-analysis/data_board_auditor/scripts/recalculate_metrics.py:177``
    is a second, independent implementation tested against the same
    fixture file as this function. If the two disagree on a case, the
    BMD is the tiebreaker.
    """
    cf = list(cashflows)
    if len(cf) == 0:
        return None

    pos = 0.0
    neg = 0.0
    for c in cf:
        cf_value = float(c)
        if math.isnan(cf_value):
            return None
        if cf_value > 0:
            pos += cf_value
        elif cf_value < 0:
            neg += cf_value

    if neg == 0.0:
        return None

    return pos / abs(neg)
