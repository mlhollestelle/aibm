"""Tests for helper functions in workflow/scripts/simulate.py."""

import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("pandas")

from aibm.poi import POI

# ---------------------------------------------------------------------------
# Import _zone_poi_counts from the workflow script.
# We load the module by file path so that its own sys.path manipulation
# (adding workflow/scripts for _config) works correctly at import time.
# ---------------------------------------------------------------------------

_SIMULATE_PATH = Path(__file__).parent.parent / "workflow" / "scripts" / "simulate.py"


def _import_simulate():
    spec = importlib.util.spec_from_file_location("simulate", _SIMULATE_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["simulate"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_sim = _import_simulate()
_zone_poi_counts = _sim._zone_poi_counts


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def _poi(activity_type: str, zone_id: str | None) -> POI:
    return POI(
        id="x", name="n", x=0.0, y=0.0, activity_type=activity_type, zone_id=zone_id
    )


def test_counts_matching_activity_types() -> None:
    pois = [
        _poi("work", "Z1"),
        _poi("work", "Z1"),
        _poi("work", "Z2"),
        _poi("shopping", "Z1"),
    ]
    result = _zone_poi_counts(pois, {"work"})
    assert result == {"Z1": 2, "Z2": 1}


def test_ignores_pois_with_none_zone_id() -> None:
    pois = [
        _poi("work", "Z1"),
        _poi("work", None),
    ]
    result = _zone_poi_counts(pois, {"work"})
    assert result == {"Z1": 1}
    assert None not in result


def test_zones_with_no_matching_pois_absent() -> None:
    pois = [
        _poi("shopping", "Z1"),
        _poi("leisure", "Z2"),
    ]
    result = _zone_poi_counts(pois, {"work"})
    assert result == {}


def test_multiple_activity_types_in_set() -> None:
    pois = [
        _poi("school", "Z1"),
        _poi("escort", "Z2"),
        _poi("work", "Z3"),
    ]
    result = _zone_poi_counts(pois, {"school", "escort"})
    assert result == {"Z1": 1, "Z2": 1}
    assert "Z3" not in result
