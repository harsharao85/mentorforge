import * as path from 'path';
import * as fs from 'fs';
import { RemovalPolicy } from 'aws-cdk-lib';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as acm from 'aws-cdk-lib/aws-certificatemanager';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as s3deploy from 'aws-cdk-lib/aws-s3-deployment';
import * as wafv2 from 'aws-cdk-lib/aws-wafv2';
import { Construct } from 'constructs';

// TASK-008 #5 — branded SPA URL. ACM cert (us-east-1, DNS-validated via Cloudflare) +
// CloudFront alternate domain. The Cloudflare CNAME demo.meringue-app.com → the
// distribution domain is grey-cloud (DNS-only). Cert/host overridable via env.
const SPA_DOMAIN   = process.env.MENTORFORGE_SPA_DOMAIN   || '';
const SPA_CERT_ARN = process.env.MENTORFORGE_SPA_CERT_ARN || '';

export class HostingConstruct extends Construct {
  public readonly distribution: cloudfront.Distribution;
  public readonly siteBucket: s3.Bucket;

  constructor(scope: Construct, id: string) {
    super(scope, id);

    // ── WAF web ACL (scope CLOUDFRONT → must be in us-east-1, which this stack is) ──
    const webAcl = new wafv2.CfnWebACL(this, 'WebAcl', {
      name: 'mentorforge-waf',
      scope: 'CLOUDFRONT',
      defaultAction: { allow: {} },
      visibilityConfig: {
        cloudWatchMetricsEnabled: true,
        metricName: 'mentorforge-waf-all',
        sampledRequestsEnabled: true,
      },
      rules: [
        {
          name: 'AWSManagedRulesCommonRuleSet',
          priority: 10,
          overrideAction: { none: {} },
          visibilityConfig: {
            cloudWatchMetricsEnabled: true,
            metricName: 'mentorforge-waf-common',
            sampledRequestsEnabled: true,
          },
          statement: {
            managedRuleGroupStatement: {
              vendorName: 'AWS',
              name: 'AWSManagedRulesCommonRuleSet',
            },
          },
        },
        {
          name: 'AWSManagedRulesKnownBadInputsRuleSet',
          priority: 20,
          overrideAction: { none: {} },
          visibilityConfig: {
            cloudWatchMetricsEnabled: true,
            metricName: 'mentorforge-waf-badinputs',
            sampledRequestsEnabled: true,
          },
          statement: {
            managedRuleGroupStatement: {
              vendorName: 'AWS',
              name: 'AWSManagedRulesKnownBadInputsRuleSet',
            },
          },
        },
        {
          // Rate-based rule — blocks IPs exceeding 1000 req in any 5-minute window.
          // Tune down to ~100 for tighter protection once real users are onboarded.
          name: 'RateLimitPerIp',
          priority: 30,
          action: { block: {} },
          visibilityConfig: {
            cloudWatchMetricsEnabled: true,
            metricName: 'mentorforge-waf-ratelimit',
            sampledRequestsEnabled: true,
          },
          statement: {
            rateBasedStatement: {
              limit: 1000,
              aggregateKeyType: 'IP',
            },
          },
        },
      ],
    });

    // ── Private S3 bucket (all public access blocked; OAC serves via CloudFront) ──
    // SSE-S3 (AES-256, $0) per ADR-019 demo encryption decision.
    this.siteBucket = new s3.Bucket(this, 'SiteBucket', {
      bucketName: undefined, // let CDK generate — stable, collision-free
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      encryption: s3.BucketEncryption.S3_MANAGED,
      enforceSSL: true,
      versioned: false,
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
    });

    // ── CloudFront OAC + distribution ──
    // Using S3BucketOrigin.withOriginAccessControl (CDK >= 2.154, current: 2.1100)
    const distribution = new cloudfront.Distribution(this, 'Distribution', {
      defaultRootObject: 'index.html',
      ...(SPA_DOMAIN && SPA_CERT_ARN ? {
        domainNames: [SPA_DOMAIN],
        certificate: acm.Certificate.fromCertificateArn(this, 'SpaCert', SPA_CERT_ARN),
      } : {}),
      minimumProtocolVersion: cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
      httpVersion: cloudfront.HttpVersion.HTTP2_AND_3,
      webAclId: webAcl.attrArn,
      defaultBehavior: {
        origin: origins.S3BucketOrigin.withOriginAccessControl(this.siteBucket),
        viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
        cachePolicy: cloudfront.CachePolicy.CACHING_OPTIMIZED,
        allowedMethods: cloudfront.AllowedMethods.ALLOW_GET_HEAD_OPTIONS,
        compress: true,
      },
      errorResponses: [
        // SPA routing — serve index.html for all 403/404 (React Router handles path)
        { httpStatus: 403, responseHttpStatus: 200, responsePagePath: '/index.html' },
        { httpStatus: 404, responseHttpStatus: 200, responsePagePath: '/index.html' },
      ],
    });

    this.distribution = distribution;

    // ── Deploy the SPA build (TASK-009) ──
    // Source is frontend/dist — run `npm --prefix frontend run build` BEFORE `cdk deploy`.
    // Falls back to aws/assets (placeholder) if the build hasn't been produced yet.
    const spaDist = path.join(__dirname, '..', '..', 'frontend', 'dist');
    const siteSource = fs.existsSync(spaDist) ? spaDist : path.join(__dirname, '..', 'assets');
    new s3deploy.BucketDeployment(this, 'PlaceholderDeploy', {
      sources: [s3deploy.Source.asset(siteSource)],
      destinationBucket: this.siteBucket,
      distribution: this.distribution,
      distributionPaths: ['/*'],
    });
  }
}
