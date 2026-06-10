# MentorForge

Open-source AI onboarding + learning platform on **Amazon Bedrock AgentCore** and an on-premises **GraphRAG** knowledge base. Organisations connect their existing content sources; an AI agent runs two experiences over one hybrid stack:

- **New-hire onboarding** — content suggestion + 1:1/group meeting scheduling driven by graph inference (V1 demo focus)
- **Ongoing Socratic learning** — teaching by asking, not answering (demo-deferred, architecture ready)

The agent reasons over a knowledge graph of your org's content *and people*. Everything runs on infrastructure the customer owns — no third-party LLM intermediary, full data residency.

---

## Architecture

```
Browser / SPA (React + Vite)
    │  WebSocket (ADR-021 signal protocol)
    ▼
Amazon Bedrock AgentCore
    ├─ Runtime (FastAPI, arm64 container)  ← Claude Sonnet via ConverseStream
    ├─ Gateway                             ← MCP tool dispatch to on-prem
    └─ Memory (DynamoDB + S3)
         │
         │  Cloudflare Tunnel / AWS Site-to-Site VPN
         ▼
On-premises VM
    ├─ Microsoft GraphRAG (Full Standard)  ← community + entity graph
    ├─ Neo4j Community Edition             ← graph store
    ├─ Ollama (Llama 3.3 70B)              ← local embeddings
    └─ FastAPI MCP server                  ← tool endpoint for the Gateway
```

Key decisions are documented in [`docs/adr/`](docs/adr/).

---

## What's in this repo

| Directory | Contents |
|---|---|
| `aws/` | CDK TypeScript stack — VPC, Cognito, AgentCore Runtime + Gateway, WebSocket API, Lambda functions, S3, DynamoDB |
| `frontend/` | React + Vite + Tailwind SPA; deployed to S3 + CloudFront |
| `on-prem/` | Docker Compose for Neo4j, Ollama, GraphRAG ingest pipeline, MCP server, dataset generator |
| `scripts/` | Demo bring-up, model switching, smoke tests, latency probe |
| `tests/` | Python unit tests (Lambda logic) + Playwright e2e specs |
| `docs/adr/` | Architecture Decision Records (durable, append-only) |

---

## Prerequisites

- AWS account, CLI configured (`aws sts get-caller-identity`)
- Node.js ≥ 18 + Python 3.12
- CDK bootstrapped: `npx cdk bootstrap aws://<ACCOUNT>/us-east-1`
- On-premises VM: Docker, 40 GB+ RAM (for GraphRAG + Llama 3.3 70B), Ollama installed natively

---

## Deploy — cloud side

```bash
cd aws
npm install

# Build the SPA first (CloudFront deploy picks up frontend/dist)
npm --prefix ../frontend install
npm --prefix ../frontend run build

# Optional: custom domain + ACM cert
export MENTORFORGE_SPA_DOMAIN=demo.your-domain.com
export MENTORFORGE_SPA_CERT_ARN=arn:aws:acm:us-east-1:<acct>:certificate/<id>

# Optional: custom model (default: Claude Sonnet 4.5)
# export MENTORFORGE_MODEL_ID=us.anthropic.claude-haiku-4-5-20251001-v1:0

npx cdk deploy
```

After deploy, note the outputs:
- `UserPoolId` / `UserPoolClientId` / `WssUrl` / `HistoryApiUrl` — update `frontend/public/config.json`

### Set a demo user password

```bash
aws cognito-idp admin-set-user-password \
  --user-pool-id <UserPoolId> \
  --username demo@northstar-consulting.demo \
  --password '<your-demo-password>' \
  --permanent
```

### Update frontend config

Edit `frontend/public/config.json` with the CDK outputs, rebuild, and re-sync to S3:

```bash
# Edit frontend/public/config.json with your stack outputs, then:
npm --prefix frontend run build
aws s3 sync frontend/dist/ s3://<SiteBucketName>/ --delete
aws cloudfront create-invalidation --distribution-id <DistributionId> --paths "/*"
```

---

## Deploy — on-premises side

```bash
cd on-prem

# 1. Generate the demo org graph + corpus
python datagen/generate_org.py          # → data/org_graph.json
python corpus/build_corpus.py           # → corpus/silver/

# 2. Run the GraphRAG pipeline (requires 40 GB+ RAM, ~2 hrs first run)
docker compose run --rm graphrag

# 3. Start Neo4j, MCP server
docker compose up -d neo4j mcp_server
```

---

## Demo

With both stacks running:

```bash
# Bring everything up and smoke-test all 3 EX stories
export MENTORFORGE_RUNTIME_ARN=<AgentRuntimeArn from CDK outputs>
./scripts/demo_up.sh
```

Open the SPA URL from the CDK `CloudFrontUrl` output (or your custom domain).

**Three EX stories to try:**
1. *"Hi, I'm Priya Nair, starting today as a Senior Consultant on the Atlas-Health engagement. What should I focus on and who should I meet?"*
2. *"I need to set up Unity Catalog governance for Atlas-Health — who has done this before?"*
3. *"I'm coming up on my 30-day mark. What should I do for my check-in?"*

---

## Cost controls

The CDK stack includes a $50/month Budget + Bedrock spend block at 100%. By default it deploys with Claude Sonnet 4.5.

For cheaper iteration during development:

```bash
# Free — no Bedrock calls (validates UI/signals/persistence)
./scripts/set_generator.sh mock

# Cheap live (~3× less than Sonnet)
./scripts/(C) set_model.sh haiku && ./scripts/set_generator.sh live

# Quality + recording
./scripts/(C) set_model.sh sonnet && ./scripts/set_generator.sh live
```

See `04 System/Cost-Aware Testing Guide.md` in the full build for details.

---

## POC vs production

This is a **proof-of-concept / demo build**. See [`docs/adr/ADR-026 — Production Deployment Architecture.md`](docs/adr/ADR-026%20—%20Production%20Deployment%20Architecture.md) for the production readiness gap analysis and the full prod backlog.

Key gaps before production use:
- Token signature verification in the WebSocket authorizer (currently skipped per ADR-010 demo carve-out)
- Multi-tenant isolation (single-tenant demo only)
- Secrets management (demo uses SSM placeholders; prod needs Secrets Manager or customer KMS)
- Wire hardening (Cloudflare Tunnel for demo; Site-to-Site VPN for prod per ADR-006/027)

---

## Architecture decisions

All major decisions are in [`docs/adr/`](docs/adr/). Key ones:

| ADR | Decision |
|---|---|
| [ADR-001](docs/adr/ADR-001%20—%20Hybrid%20Architecture%20-%20Cloud%20Reasoning,%20On-Premise%20Corpus.md) | Hybrid architecture — cloud reasoning brain, on-prem corpus |
| [ADR-002](docs/adr/ADR-002%20—%20AgentCore%20Primitives%20Selection.md) | Amazon Bedrock AgentCore as the agent platform |
| [ADR-006](docs/adr/ADR-006%20—%20Hybrid%20Wire%20Pattern.md) | Cloudflare Tunnel (demo) / Site-to-Site VPN (prod) |
| [ADR-023](docs/adr/ADR-023%20—%20Episodic%20Memory%20Model.md) | DynamoDB episodic memory + S3 artifact storage |
| [ADR-026](docs/adr/ADR-026%20—%20Production%20Deployment%20Architecture.md) | Production deployment architecture + readiness gap |

---

## License

MIT — see [LICENSE](LICENSE).
