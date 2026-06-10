---
source: {system: github, instance: northstar-github, source_id: "GITHUB_DATA_PIPELINE_STANDARDS", connector_version: "1.0"}
provenance: {author: "Data Practice Engineering", owner: "Northstar Consulting", ingested_at: "2026-05-01"}
classification: {sensitivity: internal, acl: [all-employees]}
content_meta: {type: code, title: "Data Pipeline Development Standards", tags: [data, pipeline, standards, github, python]}
---

# Data Pipeline Development Standards

**Repo:** northstar-consulting/data-standards

## Code Standards

- All pipelines must use Python 3.11+
- pytest coverage ≥ 80% on all new code
- Black + Ruff for formatting and linting
- Type hints on all public functions

## Databricks Patterns

- Use Delta Live Tables for streaming pipelines
- Unity Catalog for all data governance (see Meridian Unity Catalog Retrospective)
- Contact Dana Okafor for Unity Catalog architecture questions

## Pull Request Requirements

- One reviewer minimum; two for production code
- No self-merges
- All pipeline changes must include a runbook update
