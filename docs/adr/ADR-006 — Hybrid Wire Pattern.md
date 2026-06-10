---
tags: [adr, mentorforge, architecture]
created: 2026-06-01
adr-number: ADR-006
status: accepted
supersedes: []
superseded-by: []
extends: ["ADR-001", "ADR-002"]
---

# (C) ADR-006 — Hybrid Wire Pattern: Cloudflare Tunnel (demo) / Site-to-Site VPN (prod)

> **Date:** 2026-06-01 | **Status:** Accepted
> **Supersedes:** — | **Superseded by:** —
> **Extends:** [[ADR-001]], [[ADR-002]]

---

## Context

ADR-001 established the hybrid thesis: cloud reasoning brain in AWS, corpus on-prem. ADR-002 added AgentCore Gateway as the tool gateway — it needs to call the on-prem FastAPI MCP server to invoke graph tools. This ADR decides **how the two sides are connected**.

The wire must:
1. Allow AgentCore Gateway (in AWS) to reach the on-prem MCP server over HTTPS
2. Carry a bearer token on every MCP request (the auth layer from ADR-002 Identity)
3. Require no inbound firewall changes on the on-prem host for the demo
4. Have a plausible, low-friction upgrade path to a production-grade connection

Two distinct contexts apply: the demo host (Harsha's Mac Studio, no static IP, no corporate firewall rule) and a real enterprise deployment (a hardened on-prem VM inside a corporate network perimeter).

---

## Options Considered

### Option A — Cloudflare Tunnel (demo) + Site-to-Site VPN (prod) [CHOSEN]

**Demo path:** `cloudflared` runs as a daemon on the Mac Studio. It opens an outbound TLS connection to Cloudflare's edge — no inbound port, no firewall rule, no static IP needed. Cloudflare exposes a stable named `*.cfargotunnel.com` HTTPS URL. AgentCore Gateway registers that URL as the MCP server endpoint. The on-prem MCP bearer token (stored in SSM, injected into AgentCore Gateway) authenticates every request.

**Prod path:** AWS Site-to-Site VPN between the customer's VPC and their on-prem network. Private DNS resolves the MCP server hostname. No public internet exposure.

| | Demo | Prod |
|---|---|---|
| Setup time | ~15 min | 1–2 days |
| Inbound firewall change | None | VPN endpoint only |
| Cost | $0 (Cloudflare free tier) | ~$36/mo (VPN endpoint) |
| Auth | Bearer token over HTTPS | Bearer token over private network |
| Latency | ~20–60 ms (Cloudflare PoP) | ~1–5 ms (VPN) |
| HA | Cloudflare's edge is HA | Customer configures redundancy |

### Option B — Tailscale Funnel

Tailscale Funnel exposes a local service publicly via `tailscale funnel`. Same outbound-only model as Cloudflare Tunnel.

| Pros | Cons |
|---|---|
| Dead-simple CLI (`tailscale funnel 8443`) | Requires a Tailscale account on the on-prem host + agent |
| Integrates with WireGuard mesh if customer already uses Tailscale | No prod path in this project — Tailscale is not a VPN replacement for enterprise S2S |
| | Named URL is less stable (tied to device name, can change) |

### Option C — ngrok

Similar to Cloudflare Tunnel; popular in development contexts.

| Pros | Cons |
|---|---|
| Trivial setup | Free tier URLs are random/ephemeral — must upgrade for stable URLs |
| Familiar | Less trustworthy as a prod-adjacent demo path |
| | AgentCore Gateway needs a stable URL at registration time |

### Option D — Direct Connect

AWS Direct Connect: a dedicated physical network link between AWS and the customer's data centre.

**Rejected for V1:** 1–12 week provisioning lead time, significant cost ($200–$2000/mo port fee + partner charges), requires a colocation provider. Zero relevance for a demo. Appropriate only when an enterprise customer already has Direct Connect and wants to reuse it — add as a note in the prod deployment guide.

---

## Decision

**Demo: Cloudflare Tunnel. Prod: AWS Site-to-Site VPN.**

Cloudflare Tunnel wins the demo slot because: zero firewall changes (critical for the Mac Studio demo host), free tier, stable named URL that AgentCore Gateway can register at control-plane setup time, and Cloudflare's edge is globally HA. It is the fastest path from "neo4j loaded" to "AgentCore is calling graph tools."

AWS Site-to-Site VPN wins the prod slot because: it is the standard AWS-native pattern for extending an on-prem network into a VPC, well-covered by CDK constructs, and avoids a public internet hop for production traffic.

---

## Security Model

**Demo (Cloudflare Tunnel):**
- All traffic is TLS — Cloudflare terminates inbound TLS and re-encrypts to the origin daemon
- Bearer token (`MCP_BEARER_TOKEN` from SSM) is injected into every AgentCore Gateway → MCP request via the Gateway's header configuration
- The MCP server validates the token on every request; requests without a valid token return 401
- The tunnel URL is not published; AgentCore Gateway is the only caller
- `cloudflared` binds only to `localhost:8443` on the Mac — no LAN exposure

**Prod (Site-to-Site VPN):**
- Traffic stays on the private network; bearer token still required (defence in depth)
- TLS between AgentCore Gateway Lambda and the MCP server endpoint
- Customer is responsible for VPN endpoint HA and key rotation

**Not in V1:**
- mTLS between AgentCore Gateway and the MCP server — deferred. The bearer token + TLS provides adequate security for a single-tenant demo. mTLS adds cert management overhead with no demo value. Revisit when a regulated-industry customer requires it.

---

## Consequences

### What becomes easier
- Demo can be set up in ~15 minutes on any machine with a network connection
- No DevOps or network-team coordination needed for the demo
- AgentCore Gateway tool registration can proceed immediately after `cloudflared tunnel run`

### What becomes harder
- The Cloudflare Tunnel URL is the registration-time MCP endpoint in AgentCore Gateway. If the tunnel is re-created (new tunnel ID), the Gateway tool registration must be updated. **Mitigation:** use a named tunnel (`cloudflared tunnel create mentorforge-demo`) — the URL is stable across restarts as long as the tunnel name is unchanged.
- `cloudflared` must be running on the demo host for the agent to call on-prem tools. **Mitigation:** run as a `launchd` service (Mac) so it auto-starts.

### Deployment steps (demo)

```bash
# 1. Install cloudflared
brew install cloudflare/cloudflare/cloudflared

# 2. Authenticate (one-time, links to your Cloudflare account)
cloudflared tunnel login

# 3. Create a named tunnel (one-time)
cloudflared tunnel create mentorforge-demo

# 4. Configure the tunnel (route localhost:8443 → the tunnel)
# ~/.cloudflared/config.yml:
#   tunnel: mentorforge-demo
#   credentials-file: ~/.cloudflared/<TUNNEL_ID>.json
#   ingress:
#     - service: https://localhost:8443
#       originServerName: localhost

# 5. Add a DNS record (routes <subdomain>.<your-zone>.com → tunnel)
#    OR use the free trycloudflare.com URL (no login required, ephemeral)
cloudflared tunnel route dns mentorforge-demo mcp.yourdomain.com

# 6. Run the tunnel (or install as a service)
cloudflared tunnel run mentorforge-demo

# 7. Record the public HTTPS URL — this goes into ADR-007 MCP registration
#    and into AgentCore Gateway tool registration (TASK-005)
```

For a quick demo without a Cloudflare account (ephemeral URL, no auth):
```bash
cloudflared tunnel --url https://localhost:8443
```
This prints a `https://<random>.trycloudflare.com` URL good for the session. Fine for a one-off demo; not stable enough for AgentCore Gateway registration.

### What Would Revisit This Decision

1. Cloudflare changes the free-tier tunnel policy (add cost gates or stability limits)
2. A customer already has Tailscale mesh deployed → swap Cloudflare Tunnel for Tailscale Funnel on the demo path
3. A customer requires zero third-party cloud dependency even for the demo → fall back to Option B (Tailscale self-hosted DERP) or a bastion-host SSH tunnel

---

## References

- [[ADR-001]] — hybrid thesis; residency line that creates the need for this wire
- [[ADR-002]] — AgentCore Gateway; the caller that needs the wire URL
- [[ADR-007]] — MCP tool contract; the endpoint this wire exposes
- Cloudflare Tunnel docs: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/
- AWS Site-to-Site VPN CDK: `aws-cdk-lib/aws-ec2.VpnConnection`
