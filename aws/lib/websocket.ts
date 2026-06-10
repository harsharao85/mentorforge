import * as path from 'path';
import { Duration, RemovalPolicy, Stack } from 'aws-cdk-lib';
import * as apigwv2  from 'aws-cdk-lib/aws-apigatewayv2';
import * as cognito  from 'aws-cdk-lib/aws-cognito';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as events   from 'aws-cdk-lib/aws-events';
import * as targets  from 'aws-cdk-lib/aws-events-targets';
import * as iam      from 'aws-cdk-lib/aws-iam';
import * as lambda   from 'aws-cdk-lib/aws-lambda';
import * as s3       from 'aws-cdk-lib/aws-s3';
import { Construct } from 'constructs';

interface WebSocketProps {
  userPool:              cognito.UserPool;
  appClient:             cognito.UserPoolClient;
  agentRuntimeArn:       string;
  agentRuntimeEndpoint:  string;
  memoryTable:           dynamodb.Table;
  /** Artifact body bucket (TASK-012) — sendMessage Lambda writes learners/<sub>/... objects. */
  artifactBucket:        s3.IBucket;
}

export class WebSocketConstruct extends Construct {
  public readonly api:               apigwv2.CfnApi;
  public readonly stage:             apigwv2.CfnStage;
  public readonly connectionsTable:  dynamodb.Table;
  /** wss:// URL for the deployed demo stage */
  public readonly wssUrl:            string;
  /** https:// callback URL for PostToConnection */
  public readonly callbackUrl:       string;

  constructor(scope: Construct, id: string, props: WebSocketProps) {
    super(scope, id);

    const stack   = Stack.of(this);
    const wsDir   = path.join(__dirname, '..', 'lambdas', 'ws');
    const py312   = lambda.Runtime.PYTHON_3_12;

    // ── DynamoDB connections table ───────────────────────────────────────────
    // AWS-owned encryption (free, consistent with TASK-003b).
    // TTL attribute set by connect Lambda — stale records auto-expire after 4 h.
    this.connectionsTable = new dynamodb.Table(this, 'ConnectionsTable', {
      tableName:         'MentorForgeConnections',
      partitionKey:      { name: 'connectionId', type: dynamodb.AttributeType.STRING },
      billingMode:       dynamodb.BillingMode.PAY_PER_REQUEST,
      timeToLiveAttribute: 'ttl',
      removalPolicy:     RemovalPolicy.DESTROY,
    });

    const tableEnv = { CONNECTIONS_TABLE: this.connectionsTable.tableName };

    // ── WebSocket API ────────────────────────────────────────────────────────
    this.api = new apigwv2.CfnApi(this, 'WsApi', {
      name:                    'MentorForgeWsApi',
      protocolType:            'WEBSOCKET',
      // Route selection maps {"action":"sendMessage"} → sendMessage route, etc.
      routeSelectionExpression: '$request.body.action',
    });

    this.callbackUrl = `https://${this.api.ref}.execute-api.${stack.region}.amazonaws.com/demo`;
    this.wssUrl      = `wss://${this.api.ref}.execute-api.${stack.region}.amazonaws.com/demo`;

    // ── Lambda functions ─────────────────────────────────────────────────────

    const authorizerFn = new lambda.Function(this, 'AuthorizerFn', {
      functionName: 'mentorforge-ws-authorizer',
      runtime:      py312,
      handler:      'index.handler',
      code:         lambda.Code.fromAsset(path.join(wsDir, 'authorizer')),
      timeout:      Duration.seconds(5),
      description:  '$connect REQUEST authorizer — Cognito JWT authn (ADR-021 / Ruling 2)',
      environment: {
        USER_POOL_ID:   props.userPool.userPoolId,
        APP_CLIENT_ID:  props.appClient.userPoolClientId,
      },
    });

    const connectFn = new lambda.Function(this, 'ConnectFn', {
      functionName: 'mentorforge-ws-connect',
      runtime:      py312,
      handler:      'index.handler',
      code:         lambda.Code.fromAsset(path.join(wsDir, 'connect')),
      timeout:      Duration.seconds(5),
      description:  '$connect — registers connectionId → learnerId in DynamoDB',
      environment:  tableEnv,
    });
    this.connectionsTable.grantWriteData(connectFn);

    const disconnectFn = new lambda.Function(this, 'DisconnectFn', {
      functionName: 'mentorforge-ws-disconnect',
      runtime:      py312,
      handler:      'index.handler',
      code:         lambda.Code.fromAsset(path.join(wsDir, 'disconnect')),
      timeout:      Duration.seconds(5),
      description:  '$disconnect — removes connection record',
      environment:  tableEnv,
    });
    this.connectionsTable.grantWriteData(disconnectFn);

    const sendMessageFn = new lambda.Function(this, 'SendMessageFn', {
      functionName: 'mentorforge-ws-send-message',
      runtime:      py312,
      handler:      'index.handler',
      code:         lambda.Code.fromAsset(path.join(wsDir, 'send_message')),
      timeout:      Duration.seconds(120), // API GW WS cuts the frame at 29s but Lambda keeps running; PostToConnection still works
      description:  'sendMessage/confirm/cancel — transport layer + AgentCoreGenerator (TASK-005)',
      environment: {
        ...tableEnv,
        WS_CALLBACK_URL:           this.callbackUrl,
        TURN_LIMIT:                '20',
        TURN_WINDOW_HOURS:         '1',
        AGENT_RUNTIME_ARN:         props.agentRuntimeArn,
        AGENT_RUNTIME_QUALIFIER:   props.agentRuntimeEndpoint,
        // Generator impl (TASK-008): 'agentcore' (live) | 'mock' (deterministic recording
        // safety net). Override at deploy with `cdk deploy -c generatorImpl=mock`, or flip
        // fast without a deploy via scripts/set_generator.sh.
        GENERATOR_IMPL:            (stack.node.tryGetContext('generatorImpl') as string) || 'agentcore',
        MEMORY_TABLE_NAME:         props.memoryTable.tableName,
        ARTIFACT_BUCKET_NAME:      props.artifactBucket.bucketName,
      },
    });
    this.connectionsTable.grantReadWriteData(sendMessageFn);
    props.memoryTable.grantReadWriteData(sendMessageFn);
    // sendMessage writes artifact bodies — scoped to learners/* key prefix (TASK-012).
    props.artifactBucket.grantPut(sendMessageFn, 'learners/*');

    // sendMessage needs ManageConnections to call PostToConnection
    sendMessageFn.addToRolePolicy(new iam.PolicyStatement({
      actions:   ['execute-api:ManageConnections'],
      resources: [
        `arn:aws:execute-api:${stack.region}:${stack.account}:${this.api.ref}/demo/POST/@connections/*`,
      ],
    }));

    // sendMessage needs InvokeAgentRuntime to call AgentCore (TASK-005)
    sendMessageFn.addToRolePolicy(new iam.PolicyStatement({
      actions:   ['bedrock-agentcore:InvokeAgentRuntime', 'bedrock-agentcore:InvokeAgentRuntimeForUser'],
      resources: [`${props.agentRuntimeArn}*`],
    }));

    // sendMessage self-invokes asynchronously (InvocationType=Event) to escape the 29s API GW window.
    // Use the literal ARN — referencing sendMessageFn.functionArn here creates a CDK circular dependency.
    sendMessageFn.addToRolePolicy(new iam.PolicyStatement({
      actions:   ['lambda:InvokeFunction'],
      resources: [`arn:aws:lambda:${stack.region}:${stack.account}:function:mentorforge-ws-send-message`],
    }));

    // ── Grant API Gateway permission to invoke each Lambda ───────────────────
    const apigwPrincipal = new iam.ServicePrincipal('apigateway.amazonaws.com');
    const sourceBase     = `arn:aws:execute-api:${stack.region}:${stack.account}:${this.api.ref}`;

    authorizerFn.addPermission('ApiGwInvokeAuthorizer', {
      principal:  apigwPrincipal,
      action:     'lambda:InvokeFunction',
      sourceArn:  `${sourceBase}/authorizers/*`,
    });

    connectFn.addPermission('ApiGwInvokeConnect', {
      principal:  apigwPrincipal,
      action:     'lambda:InvokeFunction',
      sourceArn:  `${sourceBase}/*/$connect`,
    });

    disconnectFn.addPermission('ApiGwInvokeDisconnect', {
      principal:  apigwPrincipal,
      action:     'lambda:InvokeFunction',
      sourceArn:  `${sourceBase}/*/$disconnect`,
    });

    sendMessageFn.addPermission('ApiGwInvokeSendMessage', {
      principal:  apigwPrincipal,
      action:     'lambda:InvokeFunction',
      sourceArn:  `${sourceBase}/*/*`,
    });

    // ── Authorizer ───────────────────────────────────────────────────────────
    const cfnAuthorizer = new apigwv2.CfnAuthorizer(this, 'ConnectAuthorizer', {
      apiId:          this.api.ref,
      authorizerType: 'REQUEST',
      // JWT is passed as a query-string param on the WS handshake URL
      // (browsers cannot set headers on WS connect). Logged in CloudWatch —
      // acceptable for demo; rotate to short-lived tokens in prod (ADR-010).
      identitySource: ['route.request.querystring.token'],
      name:           'CognitoJwtAuthorizer',
      authorizerUri:  `arn:aws:apigateway:${stack.region}:lambda:path/2015-03-31/functions/${authorizerFn.functionArn}/invocations`,
    });

    // ── Integrations ─────────────────────────────────────────────────────────
    const mkIntegration = (fn: lambda.Function, label: string) =>
      new apigwv2.CfnIntegration(this, `Integration${label}`, {
        apiId:            this.api.ref,
        integrationType:  'AWS_PROXY',
        integrationUri:   `arn:aws:apigateway:${stack.region}:lambda:path/2015-03-31/functions/${fn.functionArn}/invocations`,
      });

    const connectInt    = mkIntegration(connectFn,    'Connect');
    const disconnectInt = mkIntegration(disconnectFn, 'Disconnect');
    const sendInt       = mkIntegration(sendMessageFn,'SendMessage');

    // ── Routes ───────────────────────────────────────────────────────────────
    const connectRoute = new apigwv2.CfnRoute(this, 'RouteConnect', {
      apiId:             this.api.ref,
      routeKey:          '$connect',
      authorizationType: 'CUSTOM',
      authorizerId:      cfnAuthorizer.ref,
      target:            `integrations/${connectInt.ref}`,
    });

    const disconnectRoute = new apigwv2.CfnRoute(this, 'RouteDisconnect', {
      apiId:             this.api.ref,
      routeKey:          '$disconnect',
      authorizationType: 'NONE',
      target:            `integrations/${disconnectInt.ref}`,
    });

    // sendMessage, confirm, cancel all handled by sendMessageFn
    const msgRoutes = (['sendMessage', 'confirm', 'cancel'] as const).map(key =>
      new apigwv2.CfnRoute(this, `Route${key.charAt(0).toUpperCase() + key.slice(1)}`, {
        apiId:             this.api.ref,
        routeKey:          key,
        authorizationType: 'NONE',
        target:            `integrations/${sendInt.ref}`,
      })
    );

    // ── Stage (auto-deploy, stage-level throttling) ──────────────────────────
    // WAF cannot attach to WebSocket APIs; stage throttling is the abuse lever.
    this.stage = new apigwv2.CfnStage(this, 'WsStage', {
      apiId:      this.api.ref,
      stageName:  'demo',
      autoDeploy: true,
      defaultRouteSettings: {
        throttlingBurstLimit: 10,
        throttlingRateLimit:  5,
      },
    });

    // Stage must see all routes before auto-deploying
    this.stage.addDependency(connectRoute);
    this.stage.addDependency(disconnectRoute);
    msgRoutes.forEach(r => this.stage.addDependency(r));

    // ── Keep-warm ping (TASK-011) ────────────────────────────────────────────
    // Fires every 5 minutes to keep the sendMessage Lambda warm, eliminating the
    // ~1.5s cold-start penalty on the first demo turn. The Lambda short-circuits on
    // {_keepwarm: true} with no side effects (no DDB read, no AgentCore call).
    const keepWarmRule = new events.Rule(this, 'SendMessageKeepWarm', {
      ruleName:    'mentorforge-send-message-keepwarm',
      description: 'Keep sendMessage Lambda warm — eliminates ~1.5s cold start on first demo turn',
      schedule:    events.Schedule.rate(Duration.minutes(5)),
    });
    keepWarmRule.addTarget(new targets.LambdaFunction(sendMessageFn, {
      event: events.RuleTargetInput.fromObject({ _keepwarm: true }),
    }));
  }
}
