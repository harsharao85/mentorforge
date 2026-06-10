"""
Signal builders for the ADR-021 typed signal protocol.

Envelope: {"type": str, "turnId": str, "seq": int, "data": dict}

Server→client: thinking, token, tool_start, tool_end,
               awaiting_confirmation, action_done, error, done
Client→server: sendMessage (new turn), confirm, cancel
"""
import json


def _make(type_: str, data: dict, turn_id: str, seq: int) -> bytes:
    return json.dumps(
        {"type": type_, "turnId": turn_id, "seq": seq, "data": data},
        ensure_ascii=False,
    ).encode()


def thinking(turn_id: str, seq: int) -> bytes:
    return _make("thinking", {}, turn_id, seq)


def token(text: str, turn_id: str, seq: int) -> bytes:
    return _make("token", {"text": text}, turn_id, seq)


def tool_start(tool: str, args: dict, turn_id: str, seq: int) -> bytes:
    return _make("tool_start", {"tool": tool, "args": args}, turn_id, seq)


def tool_end(tool: str, result: str, latency_ms: int, turn_id: str, seq: int) -> bytes:
    return _make("tool_end", {"tool": tool, "result": result, "latency_ms": latency_ms}, turn_id, seq)


def awaiting_confirmation(prompt: str, action: dict, turn_id: str, seq: int) -> bytes:
    return _make("awaiting_confirmation", {"prompt": prompt, "action": action}, turn_id, seq)


def action_done(tool: str, result: str, turn_id: str, seq: int) -> bytes:
    return _make("action_done", {"tool": tool, "result": result}, turn_id, seq)


def error(message: str, turn_id: str, seq: int) -> bytes:
    return _make("error", {"message": message}, turn_id, seq)


def done(turn_id: str, seq: int) -> bytes:
    return _make("done", {}, turn_id, seq)
