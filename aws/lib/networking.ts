import * as ec2 from 'aws-cdk-lib/aws-ec2';
import { Construct } from 'constructs';

export class NetworkingConstruct extends Construct {
  public readonly vpc: ec2.Vpc;

  constructor(scope: Construct, id: string) {
    super(scope, id);

    // 2-AZ VPC with public + private-isolated subnets.
    // NAT Gateway is DEFERRED until the first private-subnet workload (TASK-004).
    // Private subnets use PRIVATE_ISOLATED (no egress) — add natGateways: 1 and
    // change to PRIVATE_WITH_EGRESS when the AgentCore / Lambda tier needs outbound.
    // Deferring saves ~$8/week idle cost for the demo.
    this.vpc = new ec2.Vpc(this, 'Vpc', {
      maxAzs: 2,
      natGateways: 0,
      subnetConfiguration: [
        {
          name: 'public',
          subnetType: ec2.SubnetType.PUBLIC,
          cidrMask: 24,
        },
        {
          name: 'private',
          subnetType: ec2.SubnetType.PRIVATE_ISOLATED,
          cidrMask: 24,
        },
      ],
    });

    // S3 Gateway Endpoint — free; avoids NAT charges for S3 traffic once NAT is added.
    this.vpc.addGatewayEndpoint('S3GatewayEndpoint', {
      service: ec2.GatewayVpcEndpointAwsService.S3,
    });
  }
}
