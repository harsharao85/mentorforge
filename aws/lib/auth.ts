import { Duration, RemovalPolicy } from 'aws-cdk-lib';
import * as cognito from 'aws-cdk-lib/aws-cognito';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import { Construct } from 'constructs';

interface AuthProps {
  distribution: cloudfront.Distribution;
}

export class AuthConstruct extends Construct {
  public readonly userPool: cognito.UserPool;
  public readonly appClient: cognito.UserPoolClient;
  public readonly hostedUiDomain: cognito.UserPoolDomain;

  constructor(scope: Construct, id: string, props: AuthProps) {
    super(scope, id);

    // ── User pool ──
    this.userPool = new cognito.UserPool(this, 'UserPool', {
      userPoolName: 'mentorforge-users',
      selfSignUpEnabled: false,   // invite-only; admin creates users
      signInAliases: { email: true },
      autoVerify: { email: true },
      standardAttributes: {
        email: { required: true, mutable: true },
        givenName: { required: false, mutable: true },
        familyName: { required: false, mutable: true },
      },
      passwordPolicy: {
        minLength: 12,
        requireUppercase: true,
        requireDigits: true,
        requireSymbols: true,
      },
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      removalPolicy: RemovalPolicy.DESTROY,

      // SAML/OIDC federation stub — wire a real enterprise IdP here when the
      // customer wants SSO (Okta / Azure AD / IAM Identity Center).
      // Example (not wired — add identityProviders: [samlProvider] to addClient below):
      //   const samlProvider = new cognito.UserPoolIdentityProviderSaml(this, 'EnterpriseSaml', {
      //     userPool: this.userPool,
      //     metadata: cognito.UserPoolIdentityProviderSamlMetadata.url('https://idp.customer.com/metadata'),
      //     name: 'EnterpriseSAML',
      //     attributeMapping: { email: cognito.ProviderAttribute.other('email') },
      //   });
    });

    // ── Hosted UI domain ──
    this.hostedUiDomain = this.userPool.addDomain('HostedUiDomain', {
      // Domain prefix must be globally unique. Modify if this conflicts.
      cognitoDomain: { domainPrefix: 'mentorforge-demo' },
    });

    // ── App client (PKCE, no secret — for public SPA) ──
    // Callback URLs reference the CloudFront distribution domain.
    // CloudFront domain is a CloudFormation token resolved at deploy time.
    const cfDomain = `https://${props.distribution.distributionDomainName}`;
    this.appClient = this.userPool.addClient('SpaClient', {
      userPoolClientName: 'mentorforge-spa',
      generateSecret: false,   // public client
      authFlows: {
        userSrp: true,         // SRP for the SPA browser flow
        userPassword: true,    // USER_PASSWORD_AUTH — demo test client uses this to get JWT without SRP
      },
      oAuth: {
        flows: { authorizationCodeGrant: true },
        scopes: [
          cognito.OAuthScope.OPENID,
          cognito.OAuthScope.EMAIL,
          cognito.OAuthScope.PROFILE,
        ],
        callbackUrls: [
          cfDomain + '/',
          'https://demo.meringue-app.com/',  // TASK-008 #5 — branded SPA URL
          'http://localhost:5173/',  // Vite dev server — remove in production
        ],
        logoutUrls: [
          cfDomain + '/',
          'https://demo.meringue-app.com/',
          'http://localhost:5173/',
        ],
      },
      preventUserExistenceErrors: true,
      enableTokenRevocation: true,
      idTokenValidity: Duration.hours(1),
      accessTokenValidity: Duration.hours(1),
      refreshTokenValidity: Duration.days(30),
    });

    // ── Demo test user ──
    // CfnUserPoolUser creates the user in FORCE_CHANGE_PASSWORD state.
    // Set a known password after deploy:
    //   aws cognito-idp admin-set-user-password \
    //     --user-pool-id <UserPoolId> \
    //     --username demo@northstar-consulting.demo \
    //     --password '<your-demo-password>' --permanent
    new cognito.CfnUserPoolUser(this, 'DemoUser', {
      userPoolId: this.userPool.userPoolId,
      username: 'demo@northstar-consulting.demo',
      messageAction: 'SUPPRESS',
      desiredDeliveryMediums: ['EMAIL'],
      userAttributes: [
        { name: 'email',          value: 'demo@northstar-consulting.demo' },
        { name: 'email_verified', value: 'true' },
        { name: 'given_name',     value: 'Demo' },
        { name: 'family_name',    value: 'User' },
      ],
    });
  }
}
