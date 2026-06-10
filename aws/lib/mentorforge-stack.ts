import { Stack, StackProps, Tags, CfnOutput } from 'aws-cdk-lib';
import { Construct } from 'constructs';

import { SecurityConstruct } from './security';
import { NetworkingConstruct } from './networking';
import { HostingConstruct } from './hosting';
import { AuthConstruct } from './auth';
import { CostConstruct } from './cost';
import { AgentCoreConstruct } from './agentcore';
import { MemoryConstruct } from './memory';
import { WebSocketConstruct } from './websocket';

export class MentorForgeStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    // ── Tags applied to every resource in the stack ──
    Tags.of(this).add('project', 'mentorforge');
    Tags.of(this).add('env',     'demo');

    // ── Build order: Security → Networking → Hosting → Auth → Cost → AgentCore → WebSocket ──
    const security   = new SecurityConstruct(this, 'Security');
    const networking = new NetworkingConstruct(this, 'Networking');
    const hosting    = new HostingConstruct(this, 'Hosting');
    const auth       = new AuthConstruct(this, 'Auth', { distribution: hosting.distribution });
    const cost       = new CostConstruct(this, 'Cost', {
      alertEmail:       'harsharao85@gmail.com',
      monthlyBudgetUsd: 50,
    });
    const agentCore = new AgentCoreConstruct(this, 'AgentCore');
    const memory    = new MemoryConstruct(this, 'Memory', {
      userPool:  auth.userPool,
      appClient: auth.appClient,
    });
    const ws = new WebSocketConstruct(this, 'WebSocket', {
      userPool:             auth.userPool,
      appClient:            auth.appClient,
      agentRuntimeArn:      agentCore.agentRuntimeArn,
      agentRuntimeEndpoint: agentCore.endpointName,
      memoryTable:          memory.memoryTable,
      artifactBucket:       memory.artifactBucket,
    });

    void cost;
    void networking;
    void security;
    void agentCore;
    void memory;

    // ── Stack outputs ──
    new CfnOutput(this, 'CloudFrontUrl', {
      value:       `https://${hosting.distribution.distributionDomainName}`,
      description: 'CloudFront URL — verify WAF + OAC are working',
      exportName:  'MentorForgeCloudFrontUrl',
    });

    new CfnOutput(this, 'UserPoolId', {
      value:       auth.userPool.userPoolId,
      description: 'Cognito User Pool ID',
      exportName:  'MentorForgeUserPoolId',
    });

    new CfnOutput(this, 'UserPoolClientId', {
      value:       auth.appClient.userPoolClientId,
      description: 'Cognito App Client ID (PKCE, no secret)',
      exportName:  'MentorForgeUserPoolClientId',
    });

    new CfnOutput(this, 'HostedUiUrl', {
      value:       auth.hostedUiDomain.baseUrl(),
      description: 'Cognito Hosted UI base URL',
    });

    new CfnOutput(this, 'DemoLoginUrl', {
      value: auth.hostedUiDomain.signInUrl(auth.appClient, {
        redirectUri: `https://${hosting.distribution.distributionDomainName}/`,
      }),
      description: 'Direct sign-in URL (demo@northstar-consulting.demo)',
    });

    new CfnOutput(this, 'VpcId', {
      value:       networking.vpc.vpcId,
      description: 'VPC ID (used by TASK-004+ private subnets)',
      exportName:  'MentorForgeVpcId',
    });

    new CfnOutput(this, 'WireParamName', {
      value:       security.wireParam.parameterName,
      description: 'SSM parameter for Cloudflare Tunnel token — set real value before ADR-006 wire',
      exportName:  'MentorForgeWireParamName',
    });

    new CfnOutput(this, 'CalendarParamName', {
      value:       security.calendarParam.parameterName,
      description: 'SSM parameter for calendar OAuth client — set real value before ADR-021 actions',
      exportName:  'MentorForgeCalendarParamName',
    });

    new CfnOutput(this, 'AgentRuntimeArn', {
      value:       agentCore.agentRuntimeArn,
      description: 'AgentCore Runtime ARN (TASK-005a — CDK-provisioned)',
      exportName:  'MentorForgeAgentRuntimeArn',
    });

    new CfnOutput(this, 'WssUrl', {
      value:       ws.wssUrl,
      description: 'WebSocket URL — use in ws_test_client.py (ADR-021)',
      exportName:  'MentorForgeWssUrl',
    });

    new CfnOutput(this, 'WsCallbackUrl', {
      value:       ws.callbackUrl,
      description: 'API GW management endpoint for PostToConnection',
      exportName:  'MentorForgeWsCallbackUrl',
    });

    new CfnOutput(this, 'ConnectionsTableName', {
      value:       ws.connectionsTable.tableName,
      description: 'DynamoDB connections table (ADR-021)',
      exportName:  'MentorForgeConnectionsTableName',
    });

    new CfnOutput(this, 'HistoryApiUrl', {
      value:       memory.historyApiUrl,
      description: 'Lambda Function URL — SPA reads threads/messages/artifacts (TASK-010)',
      exportName:  'MentorForgeHistoryApiUrl',
    });

    new CfnOutput(this, 'LearnerMemoryTableName', {
      value:       memory.memoryTable.tableName,
      description: 'DynamoDB per-learner memory table (ADR-023)',
      exportName:  'MentorForgeLearnerMemoryTableName',
    });
  }
}
