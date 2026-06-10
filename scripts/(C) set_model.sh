#!/usr/bin/env bash
# Switch the AgentCore Runtime's reasoning model for live runs.
# Requires cdk deploy (~5 min) — the model ID is baked into the Runtime env var.
#
#   ./scripts/(C) set_model.sh haiku    → Claude Haiku 4.5  (~3x cheaper than Sonnet)
#   ./scripts/(C) set_model.sh sonnet   → Claude Sonnet 4.5 (quality + recording)
#
# For $0 UI / persistence / signal tests, skip this entirely and use mock:
#   ./scripts/set_generator.sh mock     → zero Bedrock calls, deterministic
#
# QUALITY CAVEAT: the brevity system prompt (TASK-011) was tuned and validated on Sonnet.
# Use Haiku for functional/plumbing iteration only — judge response quality and record
# demos on Sonnet. See 04 System/(C) Cost-Aware Testing Guide.md for the full ladder.
#
# NOTE: this script changes MENTORFORGE_MODEL_ID only (the reasoning model).
# The generator toggle (mock vs live) is separate — use set_generator.sh for that.
# After this deploy, set_generator.sh mock still gives $0 tests with no model calls.
set -euo pipefail

HAIKU_ID="us.anthropic.claude-haiku-4-5-20251001-v1:0"
SONNET_ID="us.anthropic.claude-sonnet-4-5-20250929-v1:0"

case "${1:-}" in
  haiku)  MODEL_ID="$HAIKU_ID"  TIER="Tier 1 — cheap live iteration" ;;
  sonnet) MODEL_ID="$SONNET_ID" TIER="Tier 2 — quality + recording"  ;;
  *)
    echo "usage: $(basename "$0") haiku|sonnet" >&2
    echo "" >&2
    echo "  haiku   Claude Haiku 4.5  ($HAIKU_ID)" >&2
    echo "  sonnet  Claude Sonnet 4.5 ($SONNET_ID)  ← current default" >&2
    exit 1
    ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/../aws"

echo "Deploying AgentCore Runtime with model: $MODEL_ID"
echo "Tier: $TIER"
echo "(~5 min — CDK updates the Runtime CloudFormation stack)"
echo ""

MENTORFORGE_MODEL_ID="$MODEL_ID" cdk deploy --require-approval never

echo ""
echo "✅ MENTORFORGE_MODEL_ID → $MODEL_ID"
echo "   Takes effect at the next AgentCore Runtime container start."
echo "   To verify: aws bedrock-agentcore describe-agent-runtime-endpoint (check env vars)"
echo ""
echo "   Live test: ./scripts/set_generator.sh live && run a turn"
echo "   Back to \$0: ./scripts/set_generator.sh mock"
