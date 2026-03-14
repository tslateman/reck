"""Tests for the five-gear autonomy model."""

from __future__ import annotations

import pytest

from reck.gear import Gear, select_gear


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (0.0, Gear.FIRST),
        (0.49, Gear.FIRST),
        (0.50, Gear.SECOND),
        (0.70, Gear.THIRD),
        (0.85, Gear.FOURTH),
        (0.95, Gear.FIFTH),
        (1.0, Gear.FIFTH),
    ],
)
def test_select_gear_boundaries(confidence: float, expected: Gear) -> None:
    """Gear boundaries match DEFAULT_THRESHOLDS."""
    assert select_gear(confidence) == expected


def test_select_gear_custom_thresholds() -> None:
    """Custom thresholds override defaults."""
    custom = (0.3, 0.5, 0.7, 0.9)
    assert select_gear(0.25, custom) == Gear.FIRST
    assert select_gear(0.35, custom) == Gear.SECOND
    assert select_gear(0.55, custom) == Gear.THIRD
    assert select_gear(0.75, custom) == Gear.FOURTH
    assert select_gear(0.95, custom) == Gear.FIFTH


def test_select_gear_negative_confidence() -> None:
    """Negative confidence clamps to FIRST."""
    assert select_gear(-0.5) == Gear.FIRST


def test_select_gear_above_one() -> None:
    """Confidence > 1.0 clamps to FIFTH."""
    assert select_gear(1.5) == Gear.FIFTH
