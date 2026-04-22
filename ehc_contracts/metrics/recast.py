"""Recast project identification.

Recast projects are projects that have been restated with a companion project
carrying "Recast" in its name (same builder). In the EHC data model they are
flagged by `dp_JSB_Board.Recast == TRUE` (column K of the board sheet).

The Project Financials emitter excludes recast projects from its output PDF;
the Board Auditor independently cross-checks this exclusion. Both sides must
agree on the recast set — disagreement is a real finding, not a rounding
quirk.

Authoritative spec: EHC Business Math Dictionary (see `ehc-data-analysis/
context/EHC_Business_Math_Dictionary.xlsx` → Source Data Crosswalk sheet).

The Board Auditor does NOT import this function. It carries its own
implementation in `ehc-data-analysis/data_board_auditor/scripts/
recalculate_metrics.py`. Both are tested against
`tests/bmd_fixtures/recast_*.json`.
"""

from __future__ import annotations

from typing import Any


def identify_recast_projects(
    board: Any,
    *,
    id_col: str = "REF_ID",
    flag_col: str = "Recast",
) -> set:
    """Return the set of project IDs flagged as recast in `dp_JSB_Board`.

    Parameters
    ----------
    board : pd.DataFrame or None
        The `dp_JSB_Board` DataFrame as loaded from V3.
    id_col : str, default "REF_ID"
        Column in `board` carrying the project identifier. `REF_ID` is the
        canonical join key that maps to `qs_iGeneral.ID`.
    flag_col : str, default "Recast"
        Truthy column flagging recast projects. Accepts pandas bool, string
        ("TRUE" / "True" / "Yes"), integer (0/1), or NaN (treated as False).

    Returns
    -------
    set
        Project IDs (as stored in `board[id_col]`) where `flag_col` is
        truthy. Empty set if `board` is None, empty, or missing either
        column — callers treat this as "no recast exclusions apply."

    Notes
    -----
    * NaN values in `flag_col` are treated as False (no exclusion).
    * NaN values in `id_col` are silently dropped.
    * The function does NOT coerce ID values to int — callers that rely on
      integer IDs should cast downstream. This preserves the caller's
      identifier scheme (V3 uses numeric IDs but the dtype may be float64
      from mixed-type reads).
    """
    if board is None:
        return set()
    # Guard against pandas None-or-empty, without hard-importing pandas at
    # module load (ehc-contracts is dataframe-agnostic at the type layer).
    try:
        if board.empty:
            return set()
    except AttributeError:
        return set()

    if id_col not in board.columns or flag_col not in board.columns:
        return set()

    # Normalize flag: bool / numeric / truthy strings → Python bool. Use
    # element-wise mapping so the behavior is stable across pandas versions
    # (newer pandas emits FutureWarning for object-dtype .fillna().astype(bool)
    # and is planning to change the semantics).
    def _truthy(v):
        if v is True:
            return True
        if v is False or v is None:
            return False
        # NaN detection without hard-importing numpy
        if isinstance(v, float) and v != v:
            return False
        if isinstance(v, (int, float)):
            return bool(v)
        if isinstance(v, str):
            return v.strip().lower() in ("true", "yes", "1")
        return bool(v)

    mask = board[flag_col].map(_truthy)

    recast_rows = board.loc[mask, id_col].dropna()
    return set(recast_rows.tolist())
