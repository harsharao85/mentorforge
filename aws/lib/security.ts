import * as ssm from 'aws-cdk-lib/aws-ssm';
import { Construct } from 'constructs';

// Demo encryption: SSE-S3 + SSM Parameter Store (both $0).
// Prod hardening delta: SSE-KMS CMK + Secrets Manager + rotation — documented in ADR-019.
//
// Note: CloudFormation cannot create SecureString SSM parameters (CFN limitation).
// After deploy, upgrade placeholders to SecureString via CLI:
//   aws ssm put-parameter \
//     --name /mentorforge/demo/wire/cloudflare-tunnel-token \
//     --value 'REAL_TOKEN' --type SecureString --overwrite

export class SecurityConstruct extends Construct {
  public readonly wireParam: ssm.StringParameter;
  public readonly calendarParam: ssm.StringParameter;

  constructor(scope: Construct, id: string) {
    super(scope, id);

    this.wireParam = new ssm.StringParameter(this, 'WireToken', {
      parameterName: '/mentorforge/demo/wire/cloudflare-tunnel-token',
      stringValue:   'PLACEHOLDER',
      description:   'Cloudflare Tunnel token for on-prem MCP wire (ADR-006 / TASK-004+)',
    });

    this.calendarParam = new ssm.StringParameter(this, 'CalendarOAuth', {
      parameterName: '/mentorforge/demo/oauth/calendar-client',
      stringValue:   '{"client_id":"PLACEHOLDER","client_secret":"PLACEHOLDER"}',
      description:   'Google / M365 OAuth2 client + secret for calendar action tools (ADR-021)',
    });
  }
}
