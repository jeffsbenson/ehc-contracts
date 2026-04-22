"""Tests for ``ehc_contracts.metrics.pf_routing``.

Fixture-driven. The Board Auditor's independent implementation lives in
``ehc-data-analysis/data_board_auditor/scripts/manifest_loader.py``
(``_apply_type_routing`` + ``_PROJFIN_TYPE_SUFFIX_MAP`` + name-prefix
logic in ``_resolve_totals_recalc_key``) and is verified against this
same fixture file via the auditor's
``tests/test_auditor_bmd_parity.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ehc_contracts.metrics.pf_routing import (
    UnclassifiedMetricError,
    VALID_TYPES,
    build_value_types_dict,
    classify_value_type,
)


FIXTURE_PATH = Path(__file__).parent / "bmd_fixtures" / "pf_routing_cases.json"


def _load_fixture():
    with open(FIXTURE_PATH) as f:
        return json.load(f)


_FIXTURE = _load_fixture()


@pytest.mark.parametrize("case", _FIXTURE["cases"], ids=lambda c: c["name"])
def test_classify_case(case):
    result = classify_value_type(
        case["metric_name"],
        overrides=case.get("overrides"),
        default=case.get("default"),
    )
    assert result == case["expected_tag"], (
        f"Case '{case['name']}': got {result!r}, "
        f"expected {case['expected_tag']!r}."
    )


@pytest.mark.parametrize(
    "case", _FIXTURE["unclassified_cases"], ids=lambda c: c["name"]
)
def test_unclassified_raises(case):
    with pytest.raises(UnclassifiedMetricError):
        classify_value_type(
            case["metric_name"],
            overrides=case.get("overrides"),
            default=case.get("default"),
        )


def test_valid_types():
    assert VALID_TYPES == frozenset({"P", "F", "IGEN", "INVARIANT"})


def test_invalid_override_tag_raises():
    with pytest.raises(ValueError):
        classify_value_type("foo", overrides={"foo": "Q"})


def test_invalid_default_tag_raises():
    with pytest.raises(ValueError):
        classify_value_type("foo", default="BOGUS")


def test_build_dict_basic():
    names = ["mnth_Prof_Sources", "mnth_Act_Cost", "LB_Margin"]
    overrides = {"LB_Margin": "P"}
    out = build_value_types_dict(names, overrides=overrides)
    assert out == {
        "mnth_Prof_Sources": "P",
        "mnth_Act_Cost": "F",
        "LB_Margin": "P",
    }


def test_build_dict_with_default():
    names = ["mnth_Prof_Sources", "unknown_thing"]
    out = build_value_types_dict(names, default="INVARIANT")
    assert out == {"mnth_Prof_Sources": "P", "unknown_thing": "INVARIANT"}


def test_build_dict_collects_all_unclassified():
    """The bulk classifier must report every unclassified metric in one
    shot — matters when an emitter has ~70 keys and a refactor renames a
    subset; the author wants to see the full list, not fix one-by-one."""
    names = ["mnth_Prof_Sources", "unknown_1", "unknown_2", "unknown_3"]
    with pytest.raises(UnclassifiedMetricError) as exc:
        build_value_types_dict(names)
    msg = str(exc.value)
    assert "unknown_1" in msg
    assert "unknown_2" in msg
    assert "unknown_3" in msg


def test_build_dict_empty():
    assert build_value_types_dict([]) == {}


def test_build_dict_returns_plain_dict():
    """Downstream serializers rely on dict semantics — the return type
    must not be a subclass that json.dump could mishandle."""
    out = build_value_types_dict(["mnth_Prof_Sources"])
    assert type(out) is dict


def test_override_precedence_over_default():
    """Override must beat default even for an unclassified name."""
    result = classify_value_type(
        "unknown_name", overrides={"unknown_name": "IGEN"}, default="INVARIANT"
    )
    assert result == "IGEN"
