#!/usr/bin/env node
import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { MentorForgeStack } from '../lib/mentorforge-stack';

const app = new cdk.App();

new MentorForgeStack(app, 'MentorForge', {
  env: {
    account: app.node.tryGetContext('account') ?? process.env.CDK_DEFAULT_ACCOUNT,
    region: 'us-east-1',
  },
  description: 'MentorForge — AWS foundation: VPC, Cognito, CloudFront/WAF, SSM, cost guards',
  tags: {
    project: 'mentorforge',
    env:     'demo',
  },
});

// CI: CDK_NAG=1 activates AwsSolutions checks during cdk synth.
// Phase 1 — advisory (violations appear in synth output; the job exits 0).
// Phase 2 — add NagSuppressions for intentional demo deviations, then add
//            --strict to the CI synth command to gate on unsuppressed errors.
// See: AWS Deployment Pipeline/(C) CI-CD Plan.md § Security.
if (process.env.CDK_NAG === '1') {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { AwsSolutionsChecks } = require('cdk-nag') as typeof import('cdk-nag');
  cdk.Aspects.of(app).add(new AwsSolutionsChecks({ verbose: false }));
}
