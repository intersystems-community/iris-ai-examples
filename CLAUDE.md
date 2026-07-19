<!-- markdownlint-disable MD013 MD060 -->

# CLAUDE.md — iris-ai-examples

Project-specific rules for Claude Code when working in this repo.

## What This Repo Is

Canonical reference demos for the IRIS AI ecosystem. Two production-quality AI Hub
examples and one Python-first example. No operational data. See `AGENTS.md` for full
context before writing any code.

## Container Isolation — CRITICAL

Each example owns its own IRIS container. Never cross them.

| Container                 | Superserver port | Web port | Owned by                   |
| ------------------------- | ---------------- | -------- | -------------------------- |
| `careconnect-iris`        | 1972             | 52773    | `careconnect-sdoh/` ONLY   |
| `kgtickets-iris`          | 1972             | 52773    | `kg-ticket-resolver/` ONLY |
| `careconnect-python-iris` | 1972             | 52773    | `careconnect-python/` ONLY |

Run only the container for the example you're working on. Never start multiple examples
simultaneously unless you've remapped ports.

**Other projects' containers are off-limits from this repo:**

| Container              | Port  | DO NOT USE                    |
| ---------------------- | ----- | ----------------------------- |
| `los-iris`             | 11972 | `~/ws/productivity-framework` |
| `opsreview-iris`       | 1972  | `~/ws/opsreview`              |
| `aihub-iris-116`       | 21972 | `~/ws/aihub`                  |
| `careconnect-iris-hub` | 1973  | `~/ws/iris-ai`                |

Container registry: `~/ws/productivity-framework/tools/lab_manager/config/iris-container-registry.yaml`

## Cross-Repo Rule

Working in `iris-ai-examples`? Never commit, edit, or write files in another repo
(`~/ws/iris-ai`, `~/ws/iris-vector-graph`, etc.) without explicit permission.
Surface it, get permission first.

## Test Commands

```bash
# CareConnect SDoH eval suite (no API key, no Docker needed)
cd careconnect-sdoh/evals
python run_evals.py

# CareConnect SDoH with live containers
cd careconnect-sdoh/docker && docker compose up -d
# Run: python careconnect-sdoh/evals/run_evals.py

# KG Ticket Resolver — no dedicated test suite; use notebooks
cd kg-ticket-resolver
export IRIS_CONTAINER=kgtickets-iris
jupyter notebook notebooks/
```

## ObjectScript Development Pattern

Always compile after editing `.cls` files:

```bash
iad iris_compile <ClassName>
```

Always verify compilation succeeded:

```bash
iad iris_search <ClassName>
```

## Starting Containers

```bash
# CareConnect SDoH
cd careconnect-sdoh/docker
docker compose up -d

# KG Ticket Resolver (API key only needed for DraftKBArticle)
export OPENAI_API_KEY=sk-...
cd kg-ticket-resolver/docker
docker compose up -d

# CareConnect Python
cd careconnect-python/docker
cp ../.env.example .env  # edit API key
docker compose build
docker compose up -d iris
```

## Class Name Rules

`%AI.*` = ISC system classes (AI Hub EAP). Ships with `irishealth-community 2026.2.0AI.162.0+`.
Never use `%AI.*` against IRIS 2025.x or earlier — they do not exist.

`AI.Memory.*` = Tom Dyar's community package (`~/ws/ai-memory`). No `%` prefix.

## Test-First Policy

Write unit tests before production code. The CareConnect eval suite
(`careconnect-sdoh/evals/`) is the model: provider-agnostic, no Docker, no API key.
New tools in any example should have a corresponding eval or pytest test before merging.
