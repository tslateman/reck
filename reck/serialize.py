"""JSON serialization helpers for dataclasses containing enums and datetimes."""

from __future__ import annotations

from datetime import datetime
from enum import Enum


def default_serializer(obj: object) -> object:
    """JSON default handler for enums and datetimes."""
    if isinstance(obj, Enum):
        return obj.name
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Cannot serialize {type(obj)}")
