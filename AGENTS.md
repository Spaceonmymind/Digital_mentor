# AGENTS.md

## Project Rules

This repository contains the Digital Mentor application.

Before making changes:

1. Read `MASTER_CONTEXT.md`.
2. Inspect the current implementation relevant to the task.
3. Check `git status`.
4. Preserve existing architecture unless explicitly asked otherwise.

## Critical Invariants

- Preserve the multi-agent architecture.
- Do not replace multiple agent roles with one generic LLM.
- Polza.ai is the current AI aggregator.
- Never hardcode secrets.
- Do not commit `.env`.
- Preserve methodology versioning and old methodology versions.
- Demo mode must remain multi-agent.
- TTS is optional and must never break analysis.
- Existing functionality must not be deleted without explicit instruction.
- A-01 is the single external user-facing voice; raw internal agent traces stay technical.

## Engineering Approach

- Prefer minimal targeted changes.
- Reuse existing services, schemas, executors, and methodology models.
- Avoid duplicate abstractions.
- Do not introduce a framework just because it exists.
- Keep API contracts backward compatible where practical.
- Add/update tests for behavior changes.
- Add an Alembic migration for database schema changes.
- Do not silently modify production behavior outside the requested scope.
- Use mock/fake LLM clients in ordinary tests; pytest must not call real Polza.ai.

## Source Of Truth

Current code > `MASTER_CONTEXT.md` > README/old docs.

If `MASTER_CONTEXT.md` becomes outdated after significant architecture changes, update it in the same branch.
