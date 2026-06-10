"""
Unit tests for the ADR-021 signal protocol builders (signals.py).

These are pure functions that serialize typed wire signals to JSON bytes.
No AWS dependencies — runs without credentials in CI.
"""
import json
import pytest
import signals as s


# ── envelope shape ─────────────────────────────────────────────────────────

def test_thinking_envelope():
    raw = s.thinking("turn-abc", 0)
    ev = json.loads(raw)
    assert ev["type"] == "thinking"
    assert ev["turnId"] == "turn-abc"
    assert ev["seq"] == 0
    assert ev["data"] == {}


def test_token_text():
    raw = s.token("hello world", "turn-1", 5)
    ev = json.loads(raw)
    assert ev["type"] == "token"
    assert ev["data"]["text"] == "hello world"
    assert ev["seq"] == 5


def test_tool_start_shape():
    raw = s.tool_start("graph_retrieve", {"query": "onboarding docs"}, "t1", 2)
    ev = json.loads(raw)
    assert ev["type"] == "tool_start"
    assert ev["data"]["tool"] == "graph_retrieve"
    assert ev["data"]["args"]["query"] == "onboarding docs"


def test_tool_end_latency():
    raw = s.tool_end("graph_retrieve", "5 nodes returned", 42, "t1", 3)
    ev = json.loads(raw)
    assert ev["type"] == "tool_end"
    assert ev["data"]["latency_ms"] == 42
    assert ev["data"]["result"] == "5 nodes returned"


def test_awaiting_confirmation_shape():
    raw = s.awaiting_confirmation(
        "Book a 1:1 with Ben Okonkwo?",
        {"tool": "schedule_meeting", "with": "Ben Okonkwo"},
        "t1",
        4,
    )
    ev = json.loads(raw)
    assert ev["type"] == "awaiting_confirmation"
    assert "Ben Okonkwo" in ev["data"]["prompt"]
    assert ev["data"]["action"]["tool"] == "schedule_meeting"


def test_action_done_shape():
    raw = s.action_done("schedule_meeting", "Calendar invite sent", "t1", 5)
    ev = json.loads(raw)
    assert ev["type"] == "action_done"
    assert ev["data"]["tool"] == "schedule_meeting"
    assert "Calendar" in ev["data"]["result"]


def test_error_shape():
    raw = s.error("Something went wrong", "t1", 6)
    ev = json.loads(raw)
    assert ev["type"] == "error"
    assert ev["data"]["message"] == "Something went wrong"


def test_done_shape():
    raw = s.done("t1", 7)
    ev = json.loads(raw)
    assert ev["type"] == "done"
    assert ev["data"] == {}


# ── seq and turnId are preserved faithfully ─────────────────────────────────

@pytest.mark.parametrize("seq", [0, 1, 99, 100, 999])
def test_seq_preserved(seq):
    ev = json.loads(s.thinking("t", seq))
    assert ev["seq"] == seq


@pytest.mark.parametrize("turn_id", ["abc", "turn-123", "00000000-1111-2222-3333-444444444444"])
def test_turn_id_preserved(turn_id):
    ev = json.loads(s.done(turn_id, 0))
    assert ev["turnId"] == turn_id


# ── wire format is UTF-8 JSON bytes ────────────────────────────────────────

def test_returns_bytes():
    assert isinstance(s.thinking("t", 0), bytes)
    assert isinstance(s.token("x", "t", 0), bytes)
    assert isinstance(s.done("t", 0), bytes)


def test_unicode_preserved():
    raw = s.token("こんにちは — HIPAA compliant", "t1", 1)
    ev = json.loads(raw)
    assert "こんにちは" in ev["data"]["text"]


def test_json_parseable_all_types():
    signals = [
        s.thinking("t", 0),
        s.token("x", "t", 1),
        s.tool_start("graph_retrieve", {}, "t", 2),
        s.tool_end("graph_retrieve", "ok", 0, "t", 3),
        s.awaiting_confirmation("Confirm?", {}, "t", 4),
        s.action_done("schedule_meeting", "done", "t", 5),
        s.error("oops", "t", 6),
        s.done("t", 7),
    ]
    for sig in signals:
        parsed = json.loads(sig)
        assert "type" in parsed
        assert "turnId" in parsed
        assert "seq" in parsed
        assert "data" in parsed
