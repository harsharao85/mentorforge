"""Onboarding Concierge — operative agent definition (baked into the Runtime image).

CANONICAL SOURCE: 04 System/(C) Onboarding Concierge — Agent Definition 2026-06-08.md
This module is the operative mirror the container loads at runtime. Keep them in sync;
the dated doc is the source of truth (ADR-008 — agent definitions are versioned by date).

Governed by ADR-008 (definition format), ADR-009 (model), ADR-007 (tools), ADR-024 (auth).
"""

# ── System prompt (v2026-06-08 — TASK-011 brevity + depth-to-panel) ────────────
SYSTEM_PROMPT = """You are the Onboarding Concierge for Northstar Consulting — a warm, sharp guide who
helps a brand-new hire land softly on Day 1.

You have tools that read the company's private knowledge graph (people, content,
engagements, onboarding journeys) and one action tool that schedules meetings.

HOW YOU WORK
- Retrieve before responding. Tools in order:
  1. graph_retrieve — filter by role/practice/engagement/stage to surface the right
     content. Documents appear automatically in the learner's right-hand panel — do NOT
     list or summarise them in prose.
  2. graph_traverse with the hire's full name to resolve NAMED onboarding people
     (manager, buddy, practice_lead, engagement_lead). Use the real names it returns —
     never guess. Call explain_path(a=<hire>, b=<person>) only if you need the
     specific relationship path to explain a connection.
  Never invent people, documents, or policies — if the graph doesn't return it, say so.

RESPONSE FORMAT — KEEP IT SHORT (hard cap: ≤ 150 words in your chat reply)
- If the engagement is HIPAA- or PII-regulated: open with ONE sentence naming the
  must-read compliance policy and the immediate reason it comes first.
- Name 2–3 people to meet: real name (from graph_traverse), their relationship, one
  sentence on why they matter *today*. Nothing more per person.
- Name the single most important document by title only — it is already in the panel.
- Call schedule_meeting immediately after. Do not write transition prose before the tool call.
Do NOT write summaries, enumerate all docs, list priorities, or add Day-1 checklists in
chat. All depth lives in the right-hand panel. Chat is orientation, panel is reference.

SCHEDULING (HITL — the human is always in control)
- After your guidance, CALL schedule_meeting for the single highest-value intro.
  The `with` argument MUST be a real person's name from graph_traverse output.
- IMPORTANT: invoking the schedule_meeting tool IS how you propose a meeting. Do NOT ask
  in prose whether to schedule and then stop — that leaves no action. Always make the
  actual tool call. Calling the tool does NOT book anything; the platform pauses and asks
  the human to confirm.
- Propose exactly one meeting per turn. Never claim a meeting is booked until confirmed.

TONE
- You are on their side. First day nerves are real. Be the colleague who already
  pulled together exactly what they need."""


# ── Tool specs (Bedrock Converse toolSpec format) ──────────────────────────────
# READ tools are dispatched to AgentCore Gateway (→ on-prem MCP). schedule_meeting
# is the HITL-gated ACTION — intercepted by the loop, never dispatched to Gateway.

GRAPH_TOOL_NAMES = {"graph_retrieve", "graph_traverse", "explain_path"}
ACTION_TOOL_NAMES = {"schedule_meeting"}

TOOL_SPECS = [
    {
        "toolSpec": {
            "name": "graph_retrieve",
            "description": (
                "Retrieve onboarding content from the company knowledge graph, scoped to a new "
                "hire's context. Pass the optional role/practice/engagement/stage filters to scope "
                "retrieval to this learner (e.g. practice='Data', engagement='Atlas-Health', stage='day_1')."
            ),
            "inputSchema": {"json": {
                "type": "object",
                "properties": {
                    "query":      {"type": "string", "description": "Natural-language retrieval query."},
                    "top_k":      {"type": "integer", "description": "Max results (default 5).", "default": 5},
                    "role":       {"type": "string", "description": "Optional — scope to the hire's role, e.g. 'Senior Consultant'."},
                    "practice":   {"type": "string", "description": "Optional — scope to the practice, e.g. 'Data'."},
                    "engagement": {"type": "string", "description": "Optional — scope to the client engagement, e.g. 'Atlas-Health'."},
                    "stage":      {"type": "string", "description": "Optional — onboarding stage, e.g. 'day_1', 'week_1'."},
                },
                "required": ["query"],
            }},
        }
    },
    {
        "toolSpec": {
            "name": "graph_traverse",
            "description": (
                "Resolve the new hire's NAMED onboarding people from the org graph: manager, buddy, "
                "practice_lead, engagement_lead. Returns each as {name, role, relationship, why}. "
                "Use this to name the real people to meet — do not guess names."
            ),
            "inputSchema": {"json": {
                "type": "object",
                "properties": {
                    "entity": {"type": "string", "description": "The new hire's full name (e.g. 'Priya Nair')."},
                    "depth":  {"type": "integer", "description": "Fallback neighbourhood depth 1-3 if not a person (default 2).", "default": 2},
                },
                "required": ["entity"],
            }},
        }
    },
    {
        "toolSpec": {
            "name": "explain_path",
            "description": (
                "Two modes. (1) WHY meet someone: pass a and b (two names) to get the relationship "
                "path between them (e.g. a='Priya Nair', b='Lena Hofer'). (2) Citations: pass answer_id "
                "to get the provenance that grounded a prior graph_retrieve."
            ),
            "inputSchema": {"json": {
                "type": "object",
                "properties": {
                    "a":         {"type": "string", "description": "First entity name (for the why-path mode)."},
                    "b":         {"type": "string", "description": "Second entity name (for the why-path mode)."},
                    "answer_id": {"type": "string", "description": "answer_id from a prior graph_retrieve (for the provenance mode)."},
                },
            }},
        }
    },
    {
        "toolSpec": {
            "name": "schedule_meeting",
            "description": (
                "Propose scheduling ONE meeting for the new hire (e.g. a 1:1 with their manager). "
                "This does NOT book the meeting — it asks the human to confirm first. Use at most once per turn."
            ),
            "inputSchema": {"json": {
                "type": "object",
                "properties": {
                    "with": {"type": "string", "description": "Person to meet (full name as it appears in the graph)."},
                    "type": {"type": "string", "description": "Meeting type, e.g. '1:1', 'coffee', 'team intro'."},
                    "duration_min": {"type": "integer", "description": "Duration in minutes (default 30).", "default": 30},
                },
                "required": ["with"],
            }},
        }
    },
]
