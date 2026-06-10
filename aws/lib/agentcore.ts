import * as path from 'path';
import { Construct } from 'constructs';
import * as bedrockagentcore from 'aws-cdk-lib/aws-bedrockagentcore';
import * as ecr_assets      from 'aws-cdk-lib/aws-ecr-assets';
import * as iam             from 'aws-cdk-lib/aws-iam';

// TASK-005 wiring. The Onboarding Concierge agent reads these at runtime.
// GATEWAY_URL is the AgentCore Gateway MCP endpoint (provisioned out-of-band via the
// control plane per ADR-002's CDK+control-plane split — see aws/scripts/provision_gateway.sh).
// BEDROCK_MODEL_ID is the ADR-009 reasoning model. Both are overridable.
const GATEWAY_URL      = process.env.MENTORFORGE_GATEWAY_URL
  ?? 'https://mentorforgegateway-bjjaj80gzm.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp';
const GATEWAY_ARN      = process.env.MENTORFORGE_GATEWAY_ARN
  ?? 'arn:aws:bedrock-agentcore:us-east-1:ACCOUNT_ID_PLACEHOLDER:gateway/YOUR_GATEWAY_ID';
const BEDROCK_MODEL_ID = process.env.MENTORFORGE_MODEL_ID
  ?? 'us.anthropic.claude-sonnet-4-5-20250929-v1:0';

/**
 * Provisions the AgentCore Runtime and its demo endpoint.
 *
 * The Runtime wraps the hand-rolled FastAPI harness in aws/agent/ — a linux/arm64
 * container that serves GET /ping (readiness probe) and POST /invocations (agent turn).
 * CDK builds the image via DockerImageAsset and pushes it to a CDK-managed ECR repo on
 * cdk deploy, so no manual ECR steps are needed.
 *
 * See TASK-005a for the root-cause write-up and local validation gate.
 */
export class AgentCoreConstruct extends Construct {
  /** Full AgentCore Runtime ARN — pass to Lambda env + IAM policy. */
  public readonly agentRuntimeArn: string;
  /** Endpoint qualifier used in InvokeAgentRuntime calls. */
  public readonly endpointName: string;

  constructor(scope: Construct, id: string) {
    super(scope, id);

    const agentDir = path.join(__dirname, '..', 'agent');

    const runtime = new bedrockagentcore.Runtime(this, 'Runtime', {
      runtimeName:          'MentorForgeRuntime',
      agentRuntimeArtifact: bedrockagentcore.AgentRuntimeArtifact.fromAsset(agentDir, {
        platform: ecr_assets.Platform.LINUX_ARM64,
      }),
      description: 'MentorForge Onboarding Concierge agent runtime',
      environmentVariables: {
        BEDROCK_MODEL_ID: BEDROCK_MODEL_ID,
        GATEWAY_URL:      GATEWAY_URL,
        // TASK-011: reduced from 2048 → 800 to cap the final streaming round.
        // The brevity system prompt targets ≤150 words (~195 tokens); 800 gives
        // headroom for tool-round preamble while cutting the 34–45s streaming tail.
        TOKEN_BUDGET:     '800',
      },
      tags: { project: 'mentorforge', env: 'demo' },
    });

    // ── Execution-role permissions (TASK-005) ──
    // Reasoning model (ADR-009) — Converse + ConverseStream. Resource "*" is acceptable
    // for the single-tenant demo; cross-region inference profiles fan out to several
    // foundation-model ARNs, so scoping is deferred to prod hardening.
    runtime.role.addToPrincipalPolicy(new iam.PolicyStatement({
      actions:   ['bedrock:InvokeModel', 'bedrock:InvokeModelWithResponseStream'],
      resources: ['*'],
    }));
    // Call the AgentCore Gateway (SigV4 inbound = AWS_IAM, per ADR-024).
    runtime.role.addToPrincipalPolicy(new iam.PolicyStatement({
      actions:   ['bedrock-agentcore:InvokeGateway'],
      resources: [GATEWAY_ARN, `${GATEWAY_ARN}/*`],
    }));

    const endpoint = runtime.addEndpoint('mentorforge_demo_endpoint', {
      description: 'Demo endpoint — EX Stories onboarding flow',
    });

    this.agentRuntimeArn = runtime.agentRuntimeArn;
    this.endpointName    = endpoint.endpointName;
  }
}
