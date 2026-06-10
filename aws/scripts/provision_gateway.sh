#!/usr/bin/env bash
# Provision the AgentCore Gateway for MentorForge (TASK-005).
#
# This is the CONTROL-PLANE half of the CDK+control-plane split ADR-002 anticipated:
# CDK owns the Runtime + IAM + transport; this script owns the Gateway, its outbound
# credential provider, and the mcpServer target (the on-prem MCP over the Cloudflare wire).
#
# Re-run whenever the Cloudflare quick-tunnel URL changes (the demo wire is ephemeral).
# After running, set the gateway URL into the CDK env and `cdk deploy`:
#     export MENTORFORGE_GATEWAY_URL="<gatewayUrl printed below>"
#     npx cdk deploy
#
# Auth model: Gateway inbound = AWS_IAM (ADR-024); outbound to MCP = bearer via the
# API-key credential provider (ADR-006/007). Requires: live AWS creds, on-prem MCP up,
# and the tunnel reachable.
#
# Usage:  ./provision_gateway.sh <TUNNEL_BASE_URL>
#   e.g.  ./provision_gateway.sh https://continuously-avatar-tracy-associations.trycloudflare.com
set -euo pipefail

TUNNEL_BASE="${1:?Usage: provision_gateway.sh <tunnel-base-url>}"
MCP_ENDPOINT="${TUNNEL_BASE%/}/mcp"
REGION="${AWS_REGION:-us-east-1}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"

GATEWAY_NAME="MentorForgeGateway"
ROLE_NAME="MentorForgeGatewayRole"
CRED_NAME="MentorForgeMcpBearer"
TARGET_NAME="graphtools"

# Read the bearer from the on-prem .env (never echoed).
BEARER="$(grep '^MCP_BEARER_TOKEN=' "$(dirname "$0")/../../on-prem/.env" | cut -d= -f2-)"

echo "==> 1/5 API-key credential provider (outbound bearer)"
CRED_ARN="$(aws bedrock-agentcore-control create-api-key-credential-provider \
  --name "$CRED_NAME" --api-key "$BEARER" --query credentialProviderArn --output text 2>/dev/null \
  || aws bedrock-agentcore-control get-api-key-credential-provider --name "$CRED_NAME" --query credentialProviderArn --output text)"
echo "    $CRED_ARN"

echo "==> 2/5 Gateway execution role (AWS_IAM inbound)"
TRUST="{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Allow\",\"Principal\":{\"Service\":\"bedrock-agentcore.amazonaws.com\"},\"Action\":\"sts:AssumeRole\",\"Condition\":{\"StringEquals\":{\"aws:SourceAccount\":\"$ACCOUNT\"}}}]}"
ROLE_ARN="$(aws iam create-role --role-name "$ROLE_NAME" --assume-role-policy-document "$TRUST" \
  --description "AgentCore Gateway execution role for TASK-005 (reads outbound MCP bearer)" \
  --query Role.Arn --output text 2>/dev/null || aws iam get-role --role-name "$ROLE_NAME" --query Role.Arn --output text)"
aws iam put-role-policy --role-name "$ROLE_NAME" --policy-name "${ROLE_NAME}Inline" --policy-document \
  "{\"Version\":\"2012-10-17\",\"Statement\":[{\"Sid\":\"ReadOutboundBearer\",\"Effect\":\"Allow\",\"Action\":[\"secretsmanager:GetSecretValue\"],\"Resource\":\"arn:aws:secretsmanager:${REGION}:${ACCOUNT}:secret:bedrock-agentcore-identity*\"},{\"Sid\":\"TokenVault\",\"Effect\":\"Allow\",\"Action\":[\"bedrock-agentcore:GetResourceApiKey\",\"bedrock-agentcore:GetWorkloadAccessToken\"],\"Resource\":\"*\"}]}"
echo "    $ROLE_ARN"
sleep 8  # role propagation

echo "==> 3/5 Gateway (MCP protocol, AWS_IAM)"
GW_ID="$(aws bedrock-agentcore-control list-gateways --query "items[?name=='$GATEWAY_NAME'].gatewayId | [0]" --output text)"
if [ "$GW_ID" = "None" ] || [ -z "$GW_ID" ]; then
  GW_ID="$(aws bedrock-agentcore-control create-gateway --name "$GATEWAY_NAME" \
    --protocol-type MCP --authorizer-type AWS_IAM --role-arn "$ROLE_ARN" \
    --description "MentorForge on-prem graph tools over the wire (TASK-005)" \
    --query gatewayId --output text)"
fi
until [ "$(aws bedrock-agentcore-control get-gateway --gateway-identifier "$GW_ID" --query status --output text)" = "READY" ]; do
  echo "    gateway creating..."; sleep 5
done
GW_URL="$(aws bedrock-agentcore-control get-gateway --gateway-identifier "$GW_ID" --query gatewayUrl --output text)"
echo "    $GW_ID  $GW_URL"

echo "==> 4/5 mcpServer target → $MCP_ENDPOINT"
# Remove any prior target (endpoint may have changed with the tunnel), then recreate.
for tid in $(aws bedrock-agentcore-control list-gateway-targets --gateway-identifier "$GW_ID" --query "items[?name=='$TARGET_NAME'].targetId" --output text); do
  aws bedrock-agentcore-control delete-gateway-target --gateway-identifier "$GW_ID" --target-id "$tid" >/dev/null || true
  sleep 3
done
TGT_CONFIG="{\"mcp\":{\"mcpServer\":{\"endpoint\":\"$MCP_ENDPOINT\"}}}"
CRED_CONFIG="[{\"credentialProviderType\":\"API_KEY\",\"credentialProvider\":{\"apiKeyCredentialProvider\":{\"providerArn\":\"$CRED_ARN\",\"credentialParameterName\":\"Authorization\",\"credentialPrefix\":\"Bearer\",\"credentialLocation\":\"HEADER\"}}}]"
TGT_ID="$(aws bedrock-agentcore-control create-gateway-target --gateway-identifier "$GW_ID" \
  --name "$TARGET_NAME" --description "On-prem GraphRAG MCP tools via Cloudflare wire" \
  --target-configuration "$TGT_CONFIG" --credential-provider-configurations "$CRED_CONFIG" \
  --query targetId --output text)"
until [ "$(aws bedrock-agentcore-control get-gateway-target --gateway-identifier "$GW_ID" --target-id "$TGT_ID" --query status --output text)" = "READY" ]; do
  st="$(aws bedrock-agentcore-control get-gateway-target --gateway-identifier "$GW_ID" --target-id "$TGT_ID" --query status --output text)"
  [ "$st" = "FAILED" ] && { aws bedrock-agentcore-control get-gateway-target --gateway-identifier "$GW_ID" --target-id "$TGT_ID" --query statusReasons; exit 1; }
  echo "    target creating..."; sleep 5
done
echo "    target $TGT_ID READY"

echo "==> 5/5 store gateway URL in SSM"
aws ssm put-parameter --name /mentorforge/demo/gateway/url --value "$GW_URL" --type String --overwrite >/dev/null

echo
echo "DONE. Gateway URL:"
echo "  $GW_URL"
echo "Next:  export MENTORFORGE_GATEWAY_URL=\"$GW_URL\"  &&  npx cdk deploy"
