"""P/F routing classification.

Every metric in an emitter's manifest carries a ``value_types`` annotation in
``{P, F, IGEN, INVARIANT}`` that tells the Board Auditor which recalc bucket
to compare against:

  * ``P`` — from ``qs_CashFlow`` Type == "P" (proforma / investment case).
  * ``F`` — from ``qs_CashFlow`` Type == "F" (reforecast / actuals + forecast).
  * ``IGEN`` — from ``qs_iGeneral`` and invariant across P/F rows.
  * ``INVARIANT`` — a constant or derived value that does not depend on
    cashflow type (option-fee caps, watchlist flags, etc.).

Historically this logic lived in three places:

  * Dashboard     — ``pipeline/compute.py`` hand-curated ``_value_types`` dict.
  * ProjFin       — ``pipeline/compute.py`` hand-curated ``_value_types`` dict.
  * Reporting App — ``Support/emit_manifest.R`` column-name prefix heuristic
                    plus a ``derived_type_overrides`` escape hatch.

This module is the single place the name-based pattern rules live, so the
Python emitters and the R emitter share the same interpretation.

**Authority.** EHC Business Math Dictionary (``ehc-data-analysis/context/
EHC_Business_Math_Dictionary.xlsx``). Fixture cases in
``tests/bmd_fixtures/pf_routing_cases.json``.

**Auditor independence.** The Board Auditor does NOT import this module.
Its own independent routing lives in ``ehc-data-analysis/data_board_auditor/
scripts/manifest_loader.py`` (``_apply_type_routing``,
``_PROJFIN_TYPE_SUFFIX_MAP``, and the prefix logic in
``_resolve_totals_recalc_key``). Both implementations are tested against
the same fixture file. If they disagree, the BMD is the tiebreaker.
"""

from __future__ import annotations

import re
from typing import Iterable


VALID_TYPES = frozenset({"P", "F", "IGEN", "INVARIANT"})


# Pattern rules — narrow to what the Reporting App's R-side heuristic
# currently encodes. ``^mnth_Pro[f]?_`` matches both ``mnth_Prof_*`` (the
# usual case) and ``mnth_Pro_Unlev`` (the one legacy column whose prefix
# is literally truncated to "Pro_" in the manifest). Expanding these is a
# migration decision, not a bug fix; if an emitter needs a different rule,
# it should pass an explicit ``overrides`` entry.
_P_PATTERN = re.compile(r"^mnth_Pro[f]?_")
_F_PATTERN = re.compile(r"^mnth_Act_")


class UnclassifiedMetricError(ValueError):
    """A metric could not be classified and no default was provided.

    Emitter-side fail-loud guard: a silent default would let new metrics
    ship without a P/F/IGEN/INVARIANT annotation and surface only
    downstream as auditor mis-routing. Callers opt into a fallback by
    passing ``default=<tag>`` (e.g. R's totals loop passes
    ``default="INVARIANT"`` to preserve its historical fallback).
    """


def classify_value_type(
    metric_name: str,
    *,
    overrides: dict | None = None,
    default: str | None = None,
) -> str:
    """Return the value type for a metric name.

    Resolution order:

      1. ``overrides[metric_name]`` if present.
      2. Name-based pattern match — ``^mnth_Prof_`` / ``^mnth_Pro_`` → "P";
         ``^mnth_Act_`` → "F".
      3. ``default`` if provided.
      4. Raise ``UnclassifiedMetricError``.

    Parameters
    ----------
    metric_name : str
        The metric's key in the manifest (top-level or dot-path sub-key).
    overrides : dict, optional
        Caller-supplied ``{name: tag}`` map. Checked first.
    default : {"P", "F", "IGEN", "INVARIANT"}, optional
        Fallback tag when neither overrides nor patterns match.

    Returns
    -------
    str
        One of ``{"P", "F", "IGEN", "INVARIANT"}``.

    Raises
    ------
    UnclassifiedMetricError
        If no rule applies and no default is provided.
    ValueError
        If an override or default is not one of the valid types.
    """
    if overrides:
        tag = overrides.get(metric_name)
        if tag is not None:
            if tag not in VALID_TYPES:
                raise ValueError(
                    f"overrides[{metric_name!r}] = {tag!r} is not one of "
                    f"{sorted(VALID_TYPES)}"
                )
            return tag

    if _P_PATTERN.match(metric_name):
        return "P"
    if _F_PATTERN.match(metric_name):
        return "F"

    if default is not None:
        if default not in VALID_TYPES:
            raise ValueError(
                f"default = {default!r} is not one of {sorted(VALID_TYPES)}"
            )
        return default

    raise UnclassifiedMetricError(
        f"Cannot classify metric {metric_name!r}: no override, no pattern "
        f"match, no default. Either add it to the caller's overrides dict "
        f"or pass default=<tag> for a fallback."
    )


def build_value_types_dict(
    metric_names: Iterable[str],
    *,
    overrides: dict | None = None,
    default: str | None = None,
) -> dict:
    """Classify every name in ``metric_names``.

    All unclassified metrics are collected into a single
    ``UnclassifiedMetricError`` so the caller sees every drift finding at
    once — matters when an emitter carries ~70 keys and a refactor renames
    a subset.

    Parameters
    ----------
    metric_names : Iterable[str]
    overrides : dict, optional
    default : {"P", "F", "IGEN", "INVARIANT"}, optional

    Returns
    -------
    dict
        ``{name: tag}`` for every classified metric.
    """
    out: dict = {}
    unclassified: list[str] = []
    for name in metric_names:
        try:
            out[name] = classify_value_type(
                name, overrides=overrides, default=default
            )
        except UnclassifiedMetricError:
            unclassified.append(name)

    if unclassified:
        raise UnclassifiedMetricError(
            f"{len(unclassified)} metric(s) could not be classified: "
            f"{unclassified!r}. Either add them to the overrides dict or "
            f"pass default=<tag> for a fallback."
        )

    return out
