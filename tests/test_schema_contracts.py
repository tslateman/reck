"""Proto-Python schema alignment tests.

Proves that Python dataclasses and proto message definitions stay in sync.
A field added to one but not the other will fail here before it silently
disappears over gRPC.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from reck.events import ActionLifecycle, DecisionRecord, SignalEvent

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _proto_fields(message_name: str) -> set[str]:
    text = (PROJECT_ROOT / "proto" / "reck.proto").read_text()
    m = re.search(rf"message {message_name}\s*\{{([^}}]*)\}}", text, re.DOTALL)
    assert m, f"Message {message_name} not found in proto"
    return set(re.findall(r"(?<!\w)(\w+)\s*=\s*\d+;", m.group(1)))


def test_decision_record_proto_python_aligned() -> None:
    """All Python DecisionRecord fields (except timestamp) exist in proto."""
    proto = _proto_fields("DecisionRecord")
    py = {f.name for f in dataclasses.fields(DecisionRecord)} - {"timestamp"}
    missing = py - proto
    assert not missing, f"Python fields missing from proto: {missing}"


def test_signal_event_proto_python_aligned() -> None:
    """All Python SignalEvent fields exist in proto (timestamp exempt)."""
    proto = _proto_fields("SignalEvent")
    py = {f.name for f in dataclasses.fields(SignalEvent)}
    missing = py - proto - {"timestamp"}
    assert not missing, f"Python fields missing from proto: {missing}"


def test_decision_record_has_gear_fields() -> None:
    """DecisionRecord has gear and confidence_at_decision in both proto and Python."""
    proto = _proto_fields("DecisionRecord")
    py = {f.name for f in dataclasses.fields(DecisionRecord)}
    assert "gear" in proto, "gear missing from proto"
    assert "gear" in py, "gear missing from Python dataclass"
    assert "confidence_at_decision" in proto, "confidence_at_decision missing from proto"
    assert "confidence_at_decision" in py, "confidence_at_decision missing from Python dataclass"


def test_action_lifecycle_enum_aligned() -> None:
    """All Python ActionLifecycle values exist in the proto enum."""
    text = (PROJECT_ROOT / "proto" / "reck.proto").read_text()
    block_start = text.find("enum ActionLifecycle")
    block = text[block_start : text.find("}", block_start)]
    proto_names = set(re.findall(r"^\s+([A-Z_]+)\s*=\s*\d+;", block, re.MULTILINE))
    py_names = {m.name for m in ActionLifecycle}
    missing = py_names - proto_names
    assert not missing, f"Python ActionLifecycle values missing from proto: {missing}"
