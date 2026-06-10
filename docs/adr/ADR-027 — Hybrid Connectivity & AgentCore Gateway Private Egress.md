---
tags: [adr, mentorforge, architecture, production, networking]
created: 2026-06-08
adr-number: ADR-027
status: accepted
supersedes: []
superseded-by: []
refines: [ADR-006, ADR-026]
depends-on: [ADR-006, ADR-024, ADR-026]
resolves: [RR-1]
---

# (C) ADR-027 — Hybrid Connectivity & AgentCore Gateway Private Egress

> **Date:** 2026-06-08 | **Status:** Accepted | **Resolves:** ADR-026 Risk Register **RR-1** (blocker)
> **Validated against current AWS docs 2026-06-08** (sources at bottom).

---

## Context

ADR-026's EA review flagged **RR-1 (blocker):** the demo wire works because AgentCore Gateway calls a *public* HTTPS tunnel URL; production claims a *private* endpoint over VPN/DX. If Gateway egress were public-HTTPS-only, the whole production connectivity story would need a redesign. This ADR records the validation and the resulting production wire.

## Finding (validated)

**AgentCore Gateway natively supports private egress to on-prem resources — including a self-hosted MCP server reachable over Direct Connect / Site-to-Site VPN.** RR-1 is closed. No public exposure of the on-prem RAG is required in production.

**Mechanism:** a Gateway target carries a `privateEndpoint.managedVpcResource` block; AgentCore provisions an **Amazon VPC Lattice resource gateway** (an ENI) in the customer's subnets and routes target traffic privately to the MCP server's private DNS name.

```jsonc
{
  "name": "mentorforge-onprem-mcp",
  "privateEndpoint": {
    "managedVpcResource": {
      "vpcIdentifier":  "vpc-…",
      "subnetIds":      ["subnet-…", "subnet-…"],
      "securityGroupIds":["sg-…"],
      "endpointIpAddressType": "IPV4"
    }
  },
  "targetConfiguration": {
    "mcp": { "mcpServer": { "endpoint": "https://mcp.onprem.internal.example.com/mcp" } }
  }
}
```

**On-prem reachability is the customer's VPC routing, not a Gateway feature:** the resource-gateway subnets must have **routes to on-prem via Transit Gateway / Virtual Private Gateway / Cloud WAN**, which then carry traffic over **DX / S-S VPN**. So the full prod path is:

```
AgentCore Gateway → VPC Lattice resource-gateway ENI (customer subnet)
   → TGW/VGW route → Direct Connect / Site-to-Site VPN → on-prem MCP server (private DNS)
```

## Decision — production wire

1. **Prod target = `mcpServer` with `privateEndpoint` (managed VPC Lattice).** Replaces the Cloudflare quick-tunnel. The on-prem MCP endpoint is **private DNS**, resolved via Route 53 Resolver (ADR-026 R1). The ephemeral-URL/restart problem disappears — the endpoint is a stable private name.
2. **Customer provides** `vpcIdentifier` + `subnetIds` + `securityGroupIds` (CloudFormation params, ADR-026); plus the routes to on-prem (TGW/VGW). Managed Lattice for same/peered accounts; **self-managed Lattice** for cross-account without peering (via RAM).
3. **The demo→prod transition is a config swap, not a rearchitecture** — same `mcpServer` target shape; demo sets a public `endpoint`, prod adds the `privateEndpoint` block + private DNS `endpoint`. This keeps ADR-006's dual-wire story honest and cheap.

## Constraints captured (these bite if missed)

- **`privateEndpoint` forbids `NO_AUTH` inbound** (unless an interceptor Lambda is configured). **ADR-024's `AWS_IAM` inbound satisfies this** — no conflict; just *don't* run the private prod gateway with no authorizer.
- **Private-CA TLS on the MCP server:** Lattice expects a publicly-trusted cert chain — put an **internal ALB with a public ACM cert** in front of the on-prem MCP (or terminate at an in-VPC hop) and point the endpoint there. On-prem MCP behind VPN usually has an internal cert, so plan for this.
- **`routingDomain`** lets you route through an intermediate (VPC endpoint / internal LB) when the cert/domain don't line up.
- **Target-type support:** `mcpServer` ✅ and `OpenAPI` ✅ support `privateEndpoint`; **Lambda** reaches the VPC via its own ENI (no `privateEndpoint`); **Smithy** does NOT support `privateEndpoint` (support case); private **API Gateway** → use an OpenAPI target with `privateEndpoint` + `routingDomain`.
- **Managed-mode cross-account** needs VPC peering / TGW; **self-managed** enables cross-account via RAM. Mind **DNS TTL** limitations (see VPC Lattice egress doc).

## Consequences

- **RR-1 closed** — production wire is real, private, and AWS-native. The on-prem RAG is never publicly exposed (strengthens the residency/compliance moat, ADR-026 R4).
- **ADR-026 RR-5 (HA) still stands** — VPC Lattice doesn't make a single DX redundant; HA is still dual-tunnel VPN or redundant DX.
- **ADR-026 R1 (hybrid DNS + CIDR + TGW) still required** — this ADR depends on that routing being in place; it doesn't replace it.
- The Gateway execution role + security groups become part of the least-privilege surface (ADR-026 R8).

## What Would Revisit This

- AWS changes the Gateway egress model or deprecates the Lattice path.
- A client needs cross-account at scale → self-managed Lattice + RAM design.
- Smithy/private-API target needs arise → support-case features land.

## Sources (validated 2026-06-08)

- [Configure AgentCore Gateway VPC Egress for Gateway Targets](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-vpc-egress.html)
- [Connect to private resources in your VPC using VPC Lattice](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/vpc-egress-private-endpoints.html)
- [Private connectivity patterns for AgentCore Gateway Targets (Networking blog)](https://aws.amazon.com/blogs/networking-and-content-delivery/private-connectivity-patterns-for-amazon-bedrock-agentcore-gateway-targets/)
- [Protecting your data using VPC and AWS PrivateLink — AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/vpc.html)

---

*Refines ADR-006 (wire) and ADR-026 (prod). ADRs are append-only.*
