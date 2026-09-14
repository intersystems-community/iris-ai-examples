<!-- markdownlint-disable MD013 MD060 -->

# CLAUDE.md — iris-ai-examples

Project-specific rules for Claude Code when working in this repo.

## What This Repo Is

Canonical reference demos for the IRIS AI ecosystem. Three runnable examples — two
ObjectScript, one Python-first — plus `ai-hub/`, a pattern library with no stack of its
own. No operational data. See `AGENTS.md` for full context before writing any code.

## Container Isolation — CRITICAL

Each example owns its own IRIS containers. Never cross them.

| Container                    | Superserver port | Other published | Owned by                   |
| ---------------------------- | ---------------- | --------------- | -------------------------- |
| `careconnect-sdoh-iris-hub`  | 1973             | 8888 (MCP)      | `careconnect-sdoh/` ONLY   |
| `careconnect-sdoh-iris-fhir` | 1974             | 52774 (web)     | `careconnect-sdoh/` ONLY   |
| `kg-ticket-resolver-iris`    | 1972             | 52773, 8888     | `kg-ticket-resolver/` ONLY |
| `careconnect-python-iris`    | 31972            | 31773 (web)     | `careconnect-python/` ONLY |

Every example prefixes its container names with its own directory name on purpose:
container names are global to the Docker daemon, so a generic name like
`careconnect-iris-hub` can collide with an unrelated stack already running on the same
machine, and the `docker rm -f` that unblocks the collision takes down whatever owned the
name. `careconnect-sdoh/`'s compose file keeps `careconnect-iris-fhir` and
`careconnect-iris-hub` as network aliases, so in-network hostnames are unaffected. Run
`docker compose ps` from the example's own directory — `careconnect-sdoh/` declares
`name: careconnect-sdoh`, so it does not need `-p`.

Names do not collide, but **ports still can**: `kg-ticket-resolver-iris` publishes MCP on
8888 and so does `careconnect-sdoh-iris-hub`, so those two examples cannot run at the same
time without remapping. Every published port comes from an env var with a default, so
remap in `.env` rather than editing compose. `careconnect-python-iris` is clear of both.
`ai-hub/` starts no container at all.

Never start, stop, or `docker rm` a container this repo does not declare. If a name
collides, find out what owns it first.

## Test Commands

```bash
# CareConnect SDoH eval suite (no API key, no Docker needed)
cd careconnect-sdoh/evals
python run_evals.py

# CareConnect SDoH with live containers
cd careconnect-sdoh && docker compose up -d --wait
# Then: python evals/run_evals.py

# Repo hygiene guards (no Docker, no API key)
python -m pytest tests/test_repo_hygiene.py -q

# KG Ticket Resolver — no dedicated test suite; use notebooks
cd kg-ticket-resolver
export IRIS_CONTAINER=kg-ticket-resolver-iris
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
# CareConnect SDoH — the canonical compose file is the one at the example root
cd careconnect-sdoh
docker compose up -d --wait

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

`AI.Memory.*` = a separate community package, not part of AI Hub. No `%` prefix.

## Test-First Policy

Write unit tests before production code. The CareConnect eval suite
(`careconnect-sdoh/evals/`) is the model: provider-agnostic, no Docker, no API key.
New tools in any example should have a corresponding eval or pytest test before merging.

<!-- codebase-memory-mcp: Code Discovery Protocol -->

## Code Discovery Protocol (codebase-memory-mcp)

**ALWAYS use `codebase-memory-mcp` tools FIRST for any code exploration:**

- `search_graph(name_pattern/label/qn_pattern)` — find functions, classes, routes
- `trace_path(function_name, mode=calls|data_flow|cross_service)` — call chains
- `get_code_snippet(qualified_name)` — exact symbol source with precise line ranges
- `query_graph(query)` — complex Cypher patterns across the codebase graph
- `get_architecture(aspects)` — project structure overview
- `search_code(pattern)` — graph-augmented text search

Use `Grep`/`Glob`/`Read` freely for text, configs, and non-code files, and always
`Read` a file before editing it. If the project is not indexed yet, run
`index_repository` first.
