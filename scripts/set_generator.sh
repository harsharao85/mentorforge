#!/usr/bin/env bash
# Flip the send_message Lambda between the live AgentCore agent and the deterministic
# mock (TASK-008 recording safety net). Fast — updates the env var, no cdk deploy.
#
#   ./scripts/set_generator.sh mock   # deterministic scripted run (no on-prem/wire needed)
#   ./scripts/set_generator.sh live   # real AgentCore + on-prem GraphRAG
#
# NOTE: a subsequent `cdk deploy` resets this to the CDK value
#       (default 'agentcore'; bake mock with `cdk deploy -c generatorImpl=mock`).
set -euo pipefail
FN="mentorforge-ws-send-message"
case "${1:-}" in
  mock) VAL="mock" ;;
  live) VAL="agentcore" ;;
  *) echo "usage: set_generator.sh mock|live" >&2; exit 1 ;;
esac

# update-function-configuration replaces the whole env map, so merge into the current one.
CUR=$(aws lambda get-function-configuration --function-name "$FN" --query 'Environment.Variables' --output json)
NEW=$(echo "$CUR" | python3 -c "import sys,json;e=json.load(sys.stdin);e['GENERATOR_IMPL']='$VAL';print(json.dumps({'Variables':e}))")
aws lambda update-function-configuration --function-name "$FN" --environment "$NEW" >/dev/null
aws lambda wait function-updated --function-name "$FN" 2>/dev/null || true
echo "✅ $FN → GENERATOR_IMPL=$VAL"
