#!/usr/bin/env bash
# MentorForge — clean demo teardown (TASK-008). Stops the wire + on-prem containers.
# Leaves the AWS side (Gateway/Runtime/CloudFront — all idle-cheap) and native Ollama
# (a shared service) running. Pass --mock-off to also revert the Lambda to live.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "stopping named tunnel…"
pkill -f "cloudflared.*mentorforge-demo" 2>/dev/null && echo "  ✅ tunnel stopped" || echo "  (no tunnel running)"

echo "stopping Neo4j + MCP…"
( cd "$ROOT/on-prem" && docker compose stop neo4j mcp_server >/dev/null 2>&1 ) && echo "  ✅ containers stopped" || echo "  (compose stop skipped)"

if [[ "${1:-}" == "--mock-off" ]]; then
  bash "$ROOT/scripts/set_generator.sh" live
fi

echo "ℹ Ollama left running (shared). Stop with: pkill -f 'ollama serve'"
echo "ℹ AWS side (Gateway/Runtime/CloudFront) left up — idle cost is negligible."
echo "✅ demo down."
