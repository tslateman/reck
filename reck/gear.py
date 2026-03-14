"""Five-gear autonomy model for adaptive confidence.

Maps a confidence scalar to an autonomy gear that determines
decision authority. Higher gears grant more autonomy as evidence
accumulates.
"""

from __future__ import annotations

from enum import IntEnum

__all__ = ["Gear", "DEFAULT_THRESHOLDS", "select_gear"]


class Gear(IntEnum):
    FIRST = 1  # < 50%  -- alert human, wait
    SECOND = 2  # 50-70% -- suggest + require gate
    THIRD = 3  # 70-85% -- execute, close monitoring
    FOURTH = 4  # 85-95% -- execute, standard ops
    FIFTH = 5  # > 95%  -- autonomous, crystallized


DEFAULT_THRESHOLDS = (0.50, 0.70, 0.85, 0.95)


def select_gear(
    confidence: float,
    thresholds: tuple[float, ...] = DEFAULT_THRESHOLDS,
) -> Gear:
    """Map a confidence scalar to an autonomy gear.

    Thresholds define the lower bounds for gears 2-5.
    Confidence below the first threshold returns FIRST.
    Confidence at or above the last threshold returns FIFTH.
    """
    if confidence < thresholds[0]:
        return Gear.FIRST
    if confidence < thresholds[1]:
        return Gear.SECOND
    if confidence < thresholds[2]:
        return Gear.THIRD
    if confidence < thresholds[3]:
        return Gear.FOURTH
    return Gear.FIFTH
