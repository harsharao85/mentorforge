"""
ResponseGenerator interface + MockSocraticGenerator.

The seam: sendMessage Lambda calls ResponseGenerator exclusively.
TASK-005 swaps MockSocraticGenerator → AgentCoreGenerator.
Nothing in the transport (index.py) changes.

Interface contract:
  start_turn()       — yields signals from turn start up to (and including)
                       awaiting_confirmation (if a HITL gate exists) or done.
  resume_confirmed() — yields signals for the post-confirm path.
  resume_cancelled() — yields signals for the post-cancel path.
"""
import time
from abc import ABC, abstractmethod
from typing import Generator

import signals as s


class ResponseGenerator(ABC):
    @abstractmethod
    def start_turn(self, text: str, turn_id: str) -> Generator[bytes, None, None]:
        """Yield signal payloads. May pause at awaiting_confirmation."""
        ...

    @abstractmethod
    def resume_confirmed(self, pending_action: dict, turn_id: str) -> Generator[bytes, None, None]:
        """Yield signal payloads after learner confirmed a gated action."""
        ...

    @abstractmethod
    def resume_cancelled(self, pending_action: dict, turn_id: str) -> Generator[bytes, None, None]:
        """Yield signal payloads after learner cancelled a gated action."""
        ...


class MockSocraticGenerator(ResponseGenerator):
    """
    Scripted mock for TASK-004. Exercises every ADR-021 signal type.
    Implements EX Story 1 "Soft Landing" — Priya Nair, Day 1, Atlas-Health.

    TASK-005: replace this class with AgentCoreGenerator.
    The only change needed: swap the class name in index.py.
    """

    def start_turn(self, text: str, turn_id: str) -> Generator[bytes, None, None]:
        seq = 0

        # ── Error-channel test trigger ──────────────────────────────────────
        if text.strip() == "__error__":
            yield s.error("Simulated error — error channel confirmed.", turn_id, seq)
            return

        # ── Scripted Soft Landing turn ───────────────────────────────────────
        yield s.thinking(turn_id, seq); seq += 1
        time.sleep(0.3)

        yield s.token(
            "Welcome, Priya. Here is your Day 1 at Northstar Consulting.",
            turn_id, seq
        ); seq += 1
        time.sleep(0.1)

        yield s.token(
            " Let me pull up exactly what you need right now.",
            turn_id, seq
        ); seq += 1
        time.sleep(0.2)

        yield s.tool_start(
            "graph_retrieve",
            {"role": "Senior Consultant", "practice": "Data", "stage": "day_1", "engagement": "Atlas-Health"},
            turn_id, seq
        ); seq += 1
        time.sleep(0.5)

        yield s.tool_end("graph_retrieve", "4 docs · 4 people · 2 group sessions", 480, turn_id, seq); seq += 1

        yield s.token(
            " Your Day 1 reading list: the Data Practice Playbook, the HIPAA Handling Policy "
            "(Atlas-Health is HIPAA-regulated — read this today), the Atlas-Health Data Stack Runbook, "
            "and How We Run Data Engagements.",
            turn_id, seq
        ); seq += 1
        time.sleep(0.15)

        yield s.token(
            " Four people to meet today: Ben Okonkwo (your manager), Tom Rivera (your buddy), "
            "Sarah Chen (Data Practice Lead), and Lena Hofer (Atlas-Health engagement lead).",
            turn_id, seq
        ); seq += 1
        time.sleep(0.2)

        # ── HITL gate — pause here; sendMessage Lambda stores pending_action ──
        yield s.awaiting_confirmation(
            prompt="Book a 30-min 1:1 intro with your manager Ben Okonkwo today?",
            action={
                "tool":  "schedule_meeting",
                "args":  {"with": "Ben Okonkwo", "type": "1:1", "duration_min": 30},
            },
            turn_id=turn_id,
            seq=seq,
        )
        # Generator returns here — index.py stores state and waits for confirm/cancel.

    def resume_confirmed(self, pending_action: dict, turn_id: str) -> Generator[bytes, None, None]:
        seq = 100  # avoid seq collisions with the pre-gate phase

        yield s.tool_start(pending_action["tool"], pending_action["args"], turn_id, seq); seq += 1
        time.sleep(0.4)
        yield s.tool_end(pending_action["tool"], "booked", 360, turn_id, seq); seq += 1
        yield s.action_done(
            pending_action["tool"],
            "Calendar invite sent to Ben Okonkwo.",
            turn_id, seq
        ); seq += 1
        time.sleep(0.1)

        yield s.token(
            " Done — the invite is in your calendar. "
            "Next up: a 15-min coffee with your buddy Tom Rivera. "
            "He knows every shortcut at Northstar.",
            turn_id, seq
        ); seq += 1
        yield s.done(turn_id, seq)

    def resume_cancelled(self, pending_action: dict, turn_id: str) -> Generator[bytes, None, None]:
        seq = 100
        yield s.token(
            "No problem — skipped for now. "
            "You can book it any time from your journey task list.",
            turn_id, seq
        ); seq += 1
        yield s.done(turn_id, seq)
