"""Tests for ehc_contracts.metrics.recast.

Every case in `tests/bmd_fixtures/recast_cases.json` is evaluated. The Board
Auditor (in `ehc-data-analysis/data_board_auditor/`) has its own independent
implementation and is expected to pass every case in this same file. The
fixture is the contract; the two implementations are independent, testable
views of it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from ehc_contracts.metrics.recast import identify_recast_projects


FIXTURE_PATH = Path(__file__).parent / "bmd_fixtures" / "recast_cases.json"


def _load_cases():
    with open(FIXTURE_PATH) as f:
        data = json.load(f)
    return data["cases"]


def _board_from_case(board_spec):
    if board_spec is None:
        return None
    # Zero-row board still needs valid columns
    return pd.DataFrame(board_spec)


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c["name"])
def test_recast_case(case):
    board = _board_from_case(case["board"])
    result = identify_recast_projects(board)
    expected = set(case["expected_ids"])
    assert result == expected, (
        f"Case '{case['name']}': got {sorted(result)}, "
        f"expected {sorted(expected)}."
    )


def test_default_column_names():
    """Sanity — the function defaults (REF_ID, Recast) match dp_JSB_Board."""
    import inspect
    sig = inspect.signature(identify_recast_projects)
    assert sig.parameters["id_col"].default == "REF_ID"
    assert sig.parameters["flag_col"].default == "Recast"


def test_custom_column_names():
    """Callers using a renamed schema can override id_col / flag_col."""
    board = pd.DataFrame({
        "project_key": [100, 200, 300],
        "recast_flag": [True, False, True],
    })
    result = identify_recast_projects(
        board, id_col="project_key", flag_col="recast_flag"
    )
    assert result == {100, 300}


def test_returns_set_type():
    """Downstream code uses set membership — return type must be set."""
    board = pd.DataFrame({"REF_ID": [1, 2], "Recast": [True, False]})
    result = identify_recast_projects(board)
    assert isinstance(result, set)
