import * as path from 'path';
import { Duration, RemovalPolicy, Stack } from 'aws-cdk-lib';
import * as cognito  from 'aws-cdk-lib/aws-cognito';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as lambda   from 'aws-cdk-lib/aws-lambda';
import * as s3       from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';

interface MemoryProps {
  userPool:  cognito.UserPool;
  appClient: cognito.UserPoolClient;
}

export class MemoryConstruct extends Construct {
  public readonly memoryTable:    dynamodb.Table;
  /** Private S3 bucket for artifact bodies (TASK-012 — SSE-S3, per-learner key prefix). */
  public readonly artifactBucket: s3.Bucket;
  /** Lambda Function URL — SPA calls this for thread/message/artifact reads. */
  public readonly historyApiUrl:  string;

  constructor(scope: Construct, id: string, props: MemoryProps) {
    super(scope, id);

    const stack = Stack.of(this);

    // ── Artifact body store (TASK-012 — ADR-029) ────────────────────────────
    // Artifact content moved out of DynamoDB into S3. DynamoDB ARTIFACT# items
    // are now lightweight index entries (s3_key + title + preview + metadata).
    // Key layout: learners/<cognito-sub>/<thread-id>/<artifact-id>
    // CORS allows GET from demo SPA origins (presigned URLs fetched by browser).
    this.artifactBucket = new s3.Bucket(this, 'ArtifactBucket', {
      bucketName:        `mentorforge-artifacts-${stack.account}-${stack.region}`,
      encryption:        s3.BucketEncryption.S3_MANAGED,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL:        true,
      versioned:         false,
      removalPolicy:     RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      cors: [
        {
          allowedMethods: [s3.HttpMethods.GET],
          allowedOrigins: [
            'https://demo.meringue-app.com',
            'https://d29x1n3d931z8o.cloudfront.net',
          ],
          allowedHeaders: ['*'],
          maxAge: 300,
        },
      ],
    });

    // ── Durable per-learner memory table (ADR-023 demo slice) ───────────────
    // No TTL — this data must survive session exits.
    // pk = LEARNER#<cognito-sub>, sk ∈ THREAD#<id> | MSG#<tid>#<ts> | ARTIFACT#<uuid>
    this.memoryTable = new dynamodb.Table(this, 'LearnerMemoryTable', {
      tableName:    'MentorForgeLearnerMemory',
      partitionKey: { name: 'pk', type: dynamodb.AttributeType.STRING },
      sortKey:      { name: 'sk', type: dynamodb.AttributeType.STRING },
      billingMode:  dynamodb.BillingMode.PAY_PER_REQUEST,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    // ── History read API — Lambda Function URL (AuthType=NONE, JWT validated inside) ──
    // Avoids a second API Gateway construct; JWT auth done in-function (same
    // issuer/audience/expiry check as the WS authorizer).
    const historyFn = new lambda.Function(this, 'HistoryFn', {
      functionName: 'mentorforge-history-api',
      runtime:      lambda.Runtime.PYTHON_3_12,
      handler:      'index.handler',
      code:         lambda.Code.fromAsset(path.join(__dirname, '..', 'lambdas', 'history')),
      timeout:      Duration.seconds(10),
      description:  'History read API — threads, messages, artifacts + presigned S3 URLs (TASK-010/012)',
      environment: {
        MEMORY_TABLE_NAME:    this.memoryTable.tableName,
        USER_POOL_ID:         props.userPool.userPoolId,
        APP_CLIENT_ID:        props.appClient.userPoolClientId,
        COGNITO_REGION:       stack.region,
        ARTIFACT_BUCKET_NAME: this.artifactBucket.bucketName,
      },
    });
    this.memoryTable.grantReadData(historyFn);
    // History Lambda signs presigned GetObject URLs — scoped to learners/* prefix.
    this.artifactBucket.grantRead(historyFn, 'learners/*');

    const fnUrl = historyFn.addFunctionUrl({
      authType: lambda.FunctionUrlAuthType.NONE,
      cors: {
        allowedOrigins: ['*'],
        allowedHeaders: ['authorization', 'content-type'],
        allowedMethods: [lambda.HttpMethod.GET],
      },
    });

    this.historyApiUrl = fnUrl.url;
  }
}
