#!/usr/bin/env bash
# MentorForge — one-command demo bring-up (TASK-008 H2).
# Ordered, idempotent, fail-loud. Verifies every hop, ends with a 3-story smoke test.
#
#   ./scripts/demo_up.sh          # live stack (on-prem + wire + AgentCore) + smoke
#   ./scripts/demo_up.sh --mock   # recording-safety: flip the Lambda to GENERATOR_IMPL=mock
#                                  #   (deterministic; no on-prem/wire dependency)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ONPREM="$ROOT/on-prem"
WIRE_HOST="mentorforge.meringue-app.com"
TUNNEL_CONFIG="$ONPREM/cloudflared/config.yml"
GW_ID="${MENTORFORGE_GW_ID:-mentorforgegateway-bjjaj80gzm}"
RUNTIME_ID="${MENTORFORGE_RUNTIME_ID:-}"
[ -n "$RUNTIME_ID" ] || { echo "MENTORFORGE_RUNTIME_ID not set — export the AgentCore Runtime ID from CDK outputs" >&2; exit 1; }
SPA_URL="https://demo.meringue-app.com"

step() { printf '\n── %s ──\n' "$*"; }
fail() { printf '❌ %s\n' "$*" >&2; exit 1; }

# Health through the wire, bypassing stale LOCAL DNS (the Gateway uses public DNS anyway).
wire_health() {
  curl -sf --doh-url https://1.1.1.1/dns-query "https://$WIRE_HOST/health" 2>/dev/null | grep -q ok \
    || curl -sf "https://$WIRE_HOST/health" 2>/dev/null | grep -q ok
}

if [[ "${1:-}" == "--mock" ]]; then
  step "MOCK MODE (recording safety net)"
  bash "$ROOT/scripts/set_generator.sh" mock
  echo "✅ send_message → GENERATOR_IMPL=mock. SPA: $SPA_URL  (deterministic; on-prem not required)"
  exit 0
fi

# 1 — Ollama (native, Metal) + models
step "1/6 Ollama"
ollama list >/dev/null 2>&1 || { echo "starting ollama serve…"; (ollama serve >/tmp/ollama-serve.log 2>&1 &) ; sleep 3; }
OLLAMA_MODELS="$(ollama list 2>/dev/null)" || fail "ollama not responding (run: ollama serve)"
for m in "llama3.3:70b" "nomic-embed-text"; do
  grep -q "$m" <<<"$OLLAMA_MODELS" || fail "missing model: $m"
done
echo "✅ ollama up, models present"

# 2 — Neo4j + MCP server
step "2/6 Neo4j + MCP (docker compose)"
( cd "$ONPREM" && docker compose up -d neo4j mcp_server >/dev/null 2>&1 ) || fail "docker compose up failed"
for i in $(seq 1 20); do curl -sf http://localhost:8443/health >/dev/null 2>&1 && break; sleep 3; [ "$i" = 20 ] && fail "MCP /health (local) unreachable"; done
echo "✅ neo4j + mcp healthy"

# 3 — Stable wire (named tunnel → fixed hostname; restart-safe)
step "3/6 Wire (named tunnel → $WIRE_HOST)"
pgrep -f "cloudflared.*mentorforge-demo" >/dev/null 2>&1 || {
  echo "starting named tunnel…"; ( cloudflared tunnel --config "$TUNNEL_CONFIG" run mentorforge-demo >/tmp/named-tunnel.log 2>&1 & ) ; sleep 5; }
for i in $(seq 1 24); do wire_health && break; sleep 3; [ "$i" = 24 ] && fail "MCP /health unreachable THROUGH the wire ($WIRE_HOST)"; done
echo "✅ wire up; MCP reachable through $WIRE_HOST"

# 4 — Gateway target (stable hostname ⇒ normally no re-provision)
step "4/6 AgentCore Gateway target"
TGT=$(aws bedrock-agentcore-control list-gateway-targets --gateway-identifier "$GW_ID" --query "items[0].status" --output text 2>/dev/null || echo MISSING)
if [ "$TGT" != "READY" ]; then
  echo "target $TGT — re-provisioning against the stable hostname…"
  AWS_REGION=us-east-1 bash "$ROOT/aws/scripts/provision_gateway.sh" "https://$WIRE_HOST" || fail "gateway re-provision failed"
fi
echo "✅ gateway target READY"

# 5 — Runtime endpoint
step "5/6 AgentCore Runtime"
RT=$(aws bedrock-agentcore-control get-agent-runtime --agent-runtime-id "$RUNTIME_ID" --query status --output text 2>/dev/null || echo MISSING)
[ "$RT" = "READY" ] || fail "runtime not READY ($RT)"
echo "✅ runtime READY"

# 6 — Smoke (3 EX story openers, end-to-end, fail-loud)
step "6/6 Smoke test"
python3 "$ROOT/scripts/demo_smoke.py" || fail "smoke test failed — do NOT start the recording"

printf '\n🚀 DEMO UP — live stack green.\n   SPA:  %s\n   Wire: https://%s/mcp (stable)\n' "$SPA_URL" "$WIRE_HOST"
