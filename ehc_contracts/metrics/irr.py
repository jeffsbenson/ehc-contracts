"""Internal Rate of Return — Newton-Raphson on monthly cashflows, annualized ×12.

Historically implemented in four places with subtle differences:

  * Dashboard  — ``pipeline/irr.py`` — pure Python ``math``, returns ``rate×12``
    (best estimate) on non-convergence, ``None`` on NaN/Inf, ``None`` on
    empty/len<2.
  * ProjFin    — ``pipeline/irr.py`` — numpy vectorized, identical return
    semantics to Dashboard.
  * Reporting App — ``Support/theme.R`` — ``irr_custom`` with
    ``max_iter=100, tol=1e-6``, ``stop()`` on non-convergence or near-zero
    derivative. Wrapped by ``safe_irr_custom`` which returns ``NA`` on
    ``stop()``, empty, all-zero, or all-NA.
  * Auditor    — ``recalculate_metrics.py::irr_newton`` — returns ``None``
    on non-convergence, ``None`` on near-zero derivative (threshold 1e-14),
    no NaN/Inf guard, no empty guard.

All four compute the same math: Newton-Raphson on the monthly NPV,
annualized by multiplying the converged monthly rate by 12. Every
difference above is in *how they handle edge cases*, not in the core
iteration.

This shared module collapses the core into one function and exposes the
edge-case behavior via **caller-scoped flags**. This follows the
Phase 4.2 "Option C" precedent (TERM filtering): the shared primitive
takes no policy, the caller picks the behavior that preserves its
published numbers.

**Auditor independence.** The Board Auditor does NOT import this module.
Its ``irr_newton`` at ``ehc-data-analysis/data_board_auditor/scripts/
recalculate_metrics.py:161`` is a second, independent implementation.
Both are tested against the same fixture file. If they disagree on a
fixture case, the BMD is the tiebreaker.

**R twin.** The Reporting App calls an R twin at ``ehc-board-reporting-
app/Support/irr.R`` that mirrors this function's iteration exactly and
is verified against the same fixture file. No reticulate dependency.
See the Phase 4.1 decision memo for the rationale on keeping rule-based
bridges as R twins; Phase 4.3 applies the same pattern to Newton-
Raphson because (a) the function is 20 lines, (b) the algorithm hasn't
changed since 1669, and (c) adding reticulate to the Shiny deploy
surface has nontrivial operational cost.

**Authoritative spec.** EHC Business Math Dictionary (``ehc-data-analysis/
context/EHC_Business_Math_Dictionary.xlsx``). Fixture cases in
``tests/bmd_fixtures/irr_cases.json``. Tolerance for cross-implementation
parity: **±0.001 percentage points** on the annualized result (i.e.,
``1e-5`` absolute on the decimal-form IRR).
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
