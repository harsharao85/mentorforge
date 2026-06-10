import * as budgets from 'aws-cdk-lib/aws-budgets';
import * as cloudwatch from 'aws-cdk-lib/aws-cloudwatch';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as logs from 'aws-cdk-lib/aws-logs';
import * as sns from 'aws-cdk-lib/aws-sns';
import * as subscriptions from 'aws-cdk-lib/aws-sns-subscriptions';
import { Duration, RemovalPolicy } from 'aws-cdk-lib';
import { Construct } from 'constructs';

interface CostProps {
  alertEmail: string;
  monthlyBudgetUsd: number;
}

export class CostConstruct extends Construct {
  public readonly alertTopic: sns.Topic;

  constructor(scope: Construct, id: string, props: CostProps) {
    super(scope, id);

    // ── SNS topic for all billing alerts ──
    this.alertTopic = new sns.Topic(this, 'BillingAlerts', {
      displayName: 'MentorForge Billing Alerts',
    });

    // Allow AWS Budgets to publish to this topic
    this.alertTopic.addToResourcePolicy(new iam.PolicyStatement({
      sid: 'AllowBudgetsPublish',
      principals: [new iam.ServicePrincipal('budgets.amazonaws.com')],
      actions: ['sns:Publish'],
      resources: [this.alertTopic.topicArn],
    }));

    this.alertTopic.addSubscription(
      new subscriptions.EmailSubscription(props.alertEmail),
    );

    // ── AWS Budget with 3-tier alerting ──
    const budget = new budgets.CfnBudget(this, 'MonthlyCostBudget', {
      budget: {
        budgetName: 'mentorforge-monthly-cost',
        budgetType: 'COST',
        timeUnit: 'MONTHLY',
        budgetLimit: { amount: props.monthlyBudgetUsd, unit: 'USD' },
      },
      notificationsWithSubscribers: [
        {
          notification: {
            notificationType: 'ACTUAL',
            comparisonOperator: 'GREATER_THAN',
            threshold: 50,
            thresholdType: 'PERCENTAGE',
          },
          subscribers: [{ subscriptionType: 'SNS', address: this.alertTopic.topicArn }],
        },
        {
          notification: {
            notificationType: 'ACTUAL',
            comparisonOperator: 'GREATER_THAN',
            threshold: 80,
            thresholdType: 'PERCENTAGE',
          },
          subscribers: [{ subscriptionType: 'SNS', address: this.alertTopic.topicArn }],
        },
        {
          notification: {
            notificationType: 'ACTUAL',
            comparisonOperator: 'GREATER_THAN',
            threshold: 100,
            thresholdType: 'PERCENTAGE',
          },
          subscribers: [{ subscriptionType: 'SNS', address: this.alertTopic.topicArn }],
        },
      ],
    });

    // ── Budget Action — hard stop at 100% (deny Bedrock invocations) ──
    // The "spend guard" IAM policy is attached to a dedicated IAM group.
    // Add your IAM user to MentorForgeDemoUsers to be subject to the cap.
    const spendGuardPolicy = new iam.ManagedPolicy(this, 'SpendGuardPolicy', {
      managedPolicyName: 'mentorforge-spend-guard',
      description: 'Applied by Budget Action when monthly spend hits 100% — denies Bedrock and SageMaker inference',
      statements: [
        new iam.PolicyStatement({
          sid: 'DenyBedrockInference',
          effect: iam.Effect.DENY,
          actions: [
            'bedrock:InvokeModel',
            'bedrock:InvokeModelWithResponseStream',
            'bedrock:InvokeAgent',
            'bedrock:InvokeAgentWithResponseStream',
          ],
          resources: ['*'],
        }),
      ],
    });

    const demoUsersGroup = new iam.Group(this, 'DemoUsersGroup', {
      groupName: 'MentorForgeDemoUsers',
      managedPolicies: [],  // spend guard policy added by Budget Action, not here
    });

    const budgetActionRole = new iam.Role(this, 'BudgetActionRole', {
      assumedBy: new iam.ServicePrincipal('budgets.amazonaws.com'),
      description: 'IAM role assumed by AWS Budgets to apply spend guard policy',
      inlinePolicies: {
        AllowAttachDetachGroupPolicy: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              actions: [
                'iam:AttachGroupPolicy',
                'iam:DetachGroupPolicy',
              ],
              resources: [demoUsersGroup.groupArn],
            }),
          ],
        }),
      },
    });

    new budgets.CfnBudgetsAction(this, 'HardStopAction', {
      budgetName: 'mentorforge-monthly-cost',
      actionType: 'APPLY_IAM_POLICY',
      actionThreshold: {
        type: 'PERCENTAGE',
        value: 100,
      },
      executionRoleArn: budgetActionRole.roleArn,
      approvalModel: 'AUTOMATIC',
      notificationType: 'ACTUAL',
      subscribers: [{
        address: this.alertTopic.topicArn,
        type: 'SNS',
      }],
      definition: {
        iamActionDefinition: {
          policyArn: spendGuardPolicy.managedPolicyArn,
          groups: [demoUsersGroup.groupName],
        },
      },
    });

    // CfnBudgetsAction depends on budget existing first
    const cfnAction = this.node.findChild('HardStopAction') as budgets.CfnBudgetsAction;
    cfnAction.addDependency(budget);

    // ── CloudWatch billing alarm ──
    // NOTE: billing metrics require "Enable billing alerts" to be turned on in
    // Account → Billing preferences in the AWS Console (one-time setup per account).
    // Billing metrics are only published to us-east-1, which matches this stack.
    const billingAlarm = new cloudwatch.Alarm(this, 'BillingAlarm', {
      alarmName: 'mentorforge-monthly-billing',
      alarmDescription: `Monthly AWS spend exceeded $${props.monthlyBudgetUsd}`,
      metric: new cloudwatch.Metric({
        namespace: 'AWS/Billing',
        metricName: 'EstimatedCharges',
        dimensionsMap: { Currency: 'USD' },
        statistic: 'Maximum',
        period: Duration.hours(6),
      }),
      threshold: props.monthlyBudgetUsd,
      comparisonOperator: cloudwatch.ComparisonOperator.GREATER_THAN_THRESHOLD,
      evaluationPeriods: 1,
      treatMissingData: cloudwatch.TreatMissingData.NOT_BREACHING,
    });
    billingAlarm.addAlarmAction({
      bind: () => ({ alarmActionArn: this.alertTopic.topicArn }),
    });

    // ── CloudWatch log groups (retention — prevents unbounded cost) ──
    // Named here so each future Lambda / service can reference the group name.
    const retention = logs.RetentionDays.ONE_MONTH;
    [
      '/mentorforge/app',
      '/mentorforge/cloudfront-access',
      '/mentorforge/waf',
    ].forEach((logGroupName) => {
      new logs.LogGroup(this, logGroupName.replace(/\//g, '-').slice(1), {
        logGroupName,
        retention,
        removalPolicy: RemovalPolicy.DESTROY,
      });
    });

    // ── CloudWatch dashboard stub ──
    new cloudwatch.Dashboard(this, 'Dashboard', {
      dashboardName: 'MentorForge',
      widgets: [
        [
          new cloudwatch.TextWidget({
            markdown: '## MentorForge — Cost & Health\n_Add widgets as services come online (TASK-004+)_',
            width: 24,
            height: 2,
          }),
        ],
        [
          new cloudwatch.GraphWidget({
            title: 'Estimated Monthly Charges (USD)',
            left: [
              new cloudwatch.Metric({
                namespace: 'AWS/Billing',
                metricName: 'EstimatedCharges',
                dimensionsMap: { Currency: 'USD' },
                statistic: 'Maximum',
                period: Duration.hours(6),
                label: 'Total',
              }),
            ],
            width: 12,
          }),
          new cloudwatch.AlarmWidget({
            title: 'Billing Alarm',
            alarm: billingAlarm,
            width: 12,
          }),
        ],
      ],
    });
  }
}
