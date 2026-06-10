# MentorForge — AWS CDK Stack

CDK TypeScript app that deploys the MentorForge AWS foundation into **us-east-1** of the customer's own AWS account.

## What this stack creates

| Construct | Resource(s) | Notes |
|---|---|---|
| **Networking** | VPC (2 AZ), public + private-isolated subnets, S3 gateway endpoint | No NAT GW — fck-nat in prod (ADR-001) |
| **Security** | 2 SSM Parameter Store placeholders (String, $0) | Set real values via CLI before using wire/calendar |
| **Hosting** | Private S3 bucket, CloudFront OAC distribution, WAF web ACL | Managed rules + rate limit |
| **Auth** | Cognito user pool, PKCE app client, Hosted UI | Demo user + SAML/OIDC stub |
| **Cost** | AWS Budget ($50/mo), Budget Action (deny-Bedrock at 100%), SNS email alerts, CW alarm, CW dashboard | **Deploy this before any Bedrock spend** |
| **WebSocket** | API GW WebSocket API (demo stage), Cognito JWT REQUEST authorizer, 4 Lambda functions, DynamoDB connections table | ADR-021 — signal protocol + MockSocraticGenerator seam |

## Prerequisites

- AWS CLI configured (`aws sts get-caller-identity` returns your account)
- Node.js ≥ 18
- CDK bootstrapped in us-east-1: `npx cdk bootstrap aws://<ACCOUNT>/us-east-1`

## Deploy

```bash
cd aws
npm install
npx cdk synth          # validate — no deploy
npx cdk diff           # show what will change
npx cdk deploy         # deploy to us-east-1
```

### Deploy outputs

After `cdk deploy`, the stack prints:

| Output | Value |
|---|---|
| `CloudFrontUrl` | The HTTPS URL serving `index.html` — verify WAF + OAC are working |
| `HostedUiUrl` | Cognito Hosted UI base URL |
| `DemoLoginUrl` | Direct sign-in URL for the demo user |
| `UserPoolId` | Cognito pool ID |
| `UserPoolClientId` | PKCE + `USER_PASSWORD_AUTH` client ID |
| `VpcId` | VPC ID (private subnets, no NAT GW) |
| `WireParamName` | SSM param name for Cloudflare Tunnel token — populate before ADR-006 wire |
| `CalendarParamName` | SSM param name for calendar OAuth client — populate before ADR-021 actions |
| `WssUrl` | WebSocket URL — paste into `ws_test_client.py` |
| `WsCallbackUrl` | API GW management endpoint for `PostToConnection` (Lambda env var) |
| `ConnectionsTableName` | DynamoDB connections table name |

## Post-deploy steps

### 1. Confirm SNS billing alert subscription
Check `<your-email>` for an SNS confirmation email and click the link. Without this, budget alerts don't deliver.

### 2. Enable billing alerts in the AWS Console
In **Account → Billing preferences → Alert preferences**, enable:
- [ ] AWS Free Tier alerts
- [ ] CloudWatch billing alerts

The CloudWatch billing alarm in this stack will not fire until this is enabled.

### 3. Set the demo user password
The demo user is created in `FORCE_CHANGE_PASSWORD` state. Set a known password:
```bash
aws cognito-idp admin-set-user-password \
  --user-pool-id <UserPoolId from outputs> \
  --username demo@northstar-consulting.demo \
  --password '<your-demo-password>' \
  --permanent
```

### 4. Verify CloudFront + WAF
Open the `CloudFrontUrl` output in a browser — should serve the placeholder `index.html` over HTTPS.

### 5. Add your IAM user to `MentorForgeDemoUsers` group
The Budget Action at 100% applies a deny-Bedrock policy to this IAM group. Add yourself:
```bash
aws iam add-user-to-group --group-name MentorForgeDemoUsers --user-name <your-iam-user>
```

## Manual Cognito login verify

1. Open `DemoLoginUrl` output in a browser
2. Sign in with `demo@northstar-consulting.demo` / `<your-demo-password>`
3. Cognito redirects to `<CloudFrontUrl>/?code=...` (auth code)
4. Success — JWT is issued; PKCE exchange would complete from the SPA (TASK-004+)

## NAT Gateway — deferred (TASK-004)

The private subnets use `PRIVATE_ISOLATED` (no egress) to avoid the ~$8/week idle NAT GW cost during the foundation phase. When TASK-004 deploys private Lambda/AgentCore workloads that need egress, add to `networking.ts`:

```diff
- subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
+ subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS,
```
and set `natGateways: 1` on the Vpc construct.

## SAML/OIDC federation — stub only

The user pool is created with `selfSignUpEnabled: false`. The SAML/OIDC provider wiring is commented out in `lib/auth.ts` — search for `samlProvider`. To connect an enterprise IdP:
1. Uncomment and configure `UserPoolIdentityProviderSaml`
2. Add the provider to `identityProviders` on the app client
3. Redeploy

## Teardown

```bash
npx cdk destroy
```

> **Note:** The Cognito user pool, S3 bucket, and SSM parameters all have `RemovalPolicy.DESTROY`. Everything is deleted cleanly. The Budget and its action are NOT destroyed by CloudFormation by default — delete them manually in the Billing console if needed.

## WebSocket API — TASK-004 (ADR-021)

The stack now includes a WebSocket API Gateway with:

- **REQUEST authorizer** — validates a Cognito ID token passed as `?token=<jwt>` on the handshake URL (browsers can't set headers on WS connect; ADR-010 marks this as a prod hardening point)
- **`$connect`** — registers `connectionId → learnerId` in DynamoDB (4-hour TTL)
- **`$disconnect`** — removes the connection record
- **`sendMessage / confirm / cancel`** → single Lambda with the `MockSocraticGenerator` (EX Story 1: Priya Nair / Soft Landing) + per-user turn cap (20 turns/hour)
- **Stage throttle** — 10 burst / 5 rate (no WAF on WebSocket APIs; this is the abuse lever)

> **ADR-010 re-check:** The `$connect` authorizer validates `iss`, `aud`, and `exp` via the Cognito JWKS endpoint but skips RSA signature verification (marked `# TODO ADR-010/prod` in the Lambda). Acceptable for demo. Before production, either verify the signature in the Lambda or swap to a Lambda authorizer that calls `cognito-idp:GetUser` to validate the token server-side. RBAC is `NONE` per ADR-021 Ruling 2 (single learner per connection; no cross-learner access possible).

### Getting a JWT for the test client

The SPA client has both `USER_SRP_AUTH` (browser flow) and `USER_PASSWORD_AUTH` (CLI/test) enabled.

```bash
# Option A — let ws_test_client.py authenticate for you (recommended)
pip install websockets boto3
python scripts/ws_test_client.py \
    --wss-url  <WssUrl output> \
    --pool-id  <UserPoolId output> \
    --client-id <UserPoolClientId output> \
    --username  demo@northstar-consulting.demo \
    --password  '<your-demo-password>'

# Option B — get a token manually then pass it
aws cognito-idp initiate-auth \
    --auth-flow USER_PASSWORD_AUTH \
    --auth-parameters USERNAME=demo@northstar-consulting.demo,PASSWORD='<your-demo-password>' \
    --client-id <UserPoolClientId output> \
    --query 'AuthenticationResult.IdToken' --output text

python scripts/ws_test_client.py \
    --wss-url <WssUrl output> \
    --token   <id-token>
```

The test client sends an EX Story 1 opener (Priya Nair, day 1, Atlas-Health engagement), prints every ADR-021 signal, and auto-confirms when `awaiting_confirmation` fires.

## Out of scope (gated on later tasks)

| Resource | Gated on |
|---|---|
| ~~API Gateway WebSocket API + `$connect` authorizer~~ | ~~TASK-004 / ADR-021~~ ✅ shipped |
| AgentCore Runtime + Memory + Gateway + Identity | TASK-005 / ADR-002 |
| Bedrock model binding | ADR-009 |
| Cloudflare Tunnel wire config | ADR-006 |
| React SPA | TASK-004+ |
| Calendar OAuth integration | ADR-021 |

## Demo vs production encryption

Demo uses SSE-S3 + SSM Parameter Store (both $0). Production hardening delta per ADR-019:
- SSE-S3 → SSE-KMS with customer-managed CMK (add `aws-kms.Key` to `SecurityConstruct`)
- SSM Parameter Store → Secrets Manager with rotation enabled

Don't add these to the CDK stack until production — they add ongoing cost with no demo value.

After deploy, upgrade SSM placeholders to SecureString via CLI:
```bash
aws ssm put-parameter \
  --name /mentorforge/demo/wire/cloudflare-tunnel-token \
  --value 'REAL_TOKEN' --type SecureString --overwrite

aws ssm put-parameter \
  --name /mentorforge/demo/oauth/calendar-client \
  --value '{"client_id":"REAL","client_secret":"REAL"}' --type SecureString --overwrite
```

## Single-stack vs multi-stack note

This is intentionally a single stack for the demo. A production deployment would split into:
- `NetworkingStack` (stable baseline, rarely updated)
- `SecurityStack` (SSM → KMS + Secrets Manager in prod, change-controlled)
- `HostingStack` (CloudFront + S3, frequently updated)
- `AuthStack` (Cognito — separate to avoid user pool recreation on unrelated changes)
- `AgentStack` (AgentCore primitives — TASK-005)
