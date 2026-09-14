# AI Hub — Contributed Patterns

Reference patterns for the **InterSystems IRIS AI Hub** framework that extend
beyond the core EAP examples. Each pattern is self-contained and designed to be
copied into your own project.

For full end-to-end applications with Docker stacks and demo data, see
[`careconnect-sdoh`](../careconnect-sdoh/) and [`kg-ticket-resolver`](../kg-ticket-resolver/).

## What's here

These patterns are **not** in the EAP sample library — they cover production
concerns (governance, observability, external MCP servers) and embedded Python.

### ObjectScript (`objectscript/cls/Sample/`)

| Pattern                      | Classes                                                                                                                                                                                | What it shows                                                                                                                                                                                                                                                      |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Jira / Atlassian MCP**     | `AI/Tools/JiraTools.cls`<br>`AI/Examples/JiraAgent.cls`                                                                                                                                | Connect a `%AI.ToolSet` to the official Atlassian Rovo MCP Server with bearer auth. Live Jira + Confluence over `<MCP><Remote>`.                                                                                                                                   |
| **ConfigStore governance**   | `AI/Examples/ConfigStoreSetup.cls`<br>`AI/Examples/ConfigStoreAgent.cls`                                                                                                               | Provider credentials + model via IRIS ConfigStore (RBAC, no hardcoded secrets). Pattern: `RegisterDefaults → SettingStore.Expand → %AI.Provider.Create → %Init()`.                                                                                                 |
| **OTel observability**       | `AI/Policies/OTelAuditPolicy.cls`<br>`AI/OTelAgent.cls`<br>`AI/Examples/OTelObservability.cls`                                                                                         | gen_ai.\* semantic convention spans via OTLP/HTTP. Pre-generate chat span ID so tool-call spans are children. W3C traceparent propagation.                                                                                                                         |
| **Python bridge governance** | `AI/Bridge/Agent.cls`<br>`AI/Bridge/AuditPolicy.cls`<br>`AI/Bridge/AuthPolicy.cls`<br>`AI/Bridge/MCPService.cls`                                                                       | Govern Python `@tool` functions via IRIS RBAC. ConfigStore provider, deny/allow-list policy, OTel on the ConfigStore path, MCP exposure of bridge-compiled tools.                                                                                                  |
| **Interop + OTel**           | `Interop/OTelBusinessOperation.cls`<br>`Interop/OTelBusinessProcess.cls`<br>`Interop/OTelBusinessService.cls`<br>`Interop/OTelSetup.cls`<br>`Interop/Examples/CareConnect*.cls`        | OTel span emission from IRIS Interoperability BS/BP/BO into a shared trace. CareConnect demo wiring included.                                                                                                                                                      |
| **OAuth 2.0 + RBAC**         | `AI/OAuth/OAuthMCPService.cls`<br>`AI/OAuth/ScopeAuthenticator.cls`<br>`AI/OAuth/RBACPolicy.cls`<br>`AI/OAuth/RoleDiscovery.cls`<br>`AI/OAuth/DemoToolSet.cls`<br>`AI/OAuth/Setup.cls` | Gate an MCP server by IdP-issued roles using the native IRIS OAuth2 Resource Server — no JWT parsing, no `OnPreServer`. Measured end to end against Keycloak 26; the [README](objectscript/cls/Sample/AI/OAuth/README.md) records the results and the sharp edges. |

### Python (`python/`)

| Pattern                     | Path                                                              | What it shows                                                                                                                                                                                    |
| --------------------------- | ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **@tool + xdev SQL + OTel** | `python/embedded/bridge_xdev_demo.py`                             | Python `@tool` functions with live IRIS SQL via `iris.dbapi` (embedded, zero TCP). `iris_tool_bridge` compiles tools into `%AI.ToolSet` at runtime. OTel spans for every LLM call and tool call. |
| **OTel helpers**            | `python/embedded/otel_spans.py`<br>`python/embedded/otel_sink.py` | `OTelEmitter` for OTLP/HTTP span emission. `OTelSink` in-process collector for testing span trees without a real collector.                                                                      |
| **iris_tool_bridge**        | `python/embedded/iris_tool_bridge.py`                             | Compile a Python `ToolSet` subclass into a named ObjectScript `%AI.ToolSet` class at runtime via `irispython`.                                                                                   |
| **RLM (Python)**            | `python/rlm/`                                                     | Python implementation of the Recursive Language Model pattern. Entry point: `run_rlm_demo.py`. DSPy and LangGraph adapters included.                                                             |
| **Session store seam**      | `python/rlm/store.py`                                             | `SessionStore` Protocol with two adapters: `IRISStore` writing `^RLM.Session` globals, and an in-memory fake. Imports without `iris_llm` or a live IRIS, so the unit tests need neither.         |

### Scripts (`scripts/`)

| Script                          | What it does                                                                                                                                                                                                                                           |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `setup_oauth_test_container.py` | Starts (or reuses) a throwaway `aihub-oauth-test` container, compiles the six `Sample.AI.OAuth` classes into `USER`, unexpires passwords, enables `%Service_CallIn`, and prints the container name. `--stop` tears it down; `--no-reuse` recreates it. |
| `run-oauth-tests.sh`            | Wraps the above, copies `tests/integration/test_oauth_rbac.py` plus the two mock classes into the container, and runs pytest under `irispython`. `--keep` leaves the container up for poking at.                                                       |

### Fixtures (`fixtures/`)

| Fixture             | What it is                                                                                                                                                          |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `fixtures/keycloak` | The IdP the OAuth example was measured against: realm `aihub`, three client-credentials clients (one per role tier), an audience mapper, and a token helper script. |

Both scripts above need `IRIS_IMAGE` set to an AI Hub IRIS image tag — there is no public
default, because `%AI.*` ships only in AI Hub builds. The setup script exits with
instructions if it is unset.

## Key gotchas

### `AddTool` — always pass an instance, not a string URI

```objectscript
// WRONG — SIGSEGV on build 136/139 for ToolSets with <MCP><Remote>
Do tAgent.ToolManager.AddTool("iris:Sample.AI.Tools.JiraTools")

// CORRECT — routes through ObjectScript AddToolSetInstance, safe
Do tAgent.ToolManager.AddTool(##class(Sample.AI.Tools.JiraTools).%New())
```

The `"iris:ClassName"` form triggers a re-entrant callin inside `$ZF(-6)`. IRIS
does not support re-entrant callin — you get signal 11. The object form is safe.

### `@{env:VAR}` expansion requires daemon-time env

Token expansion in `<MCP><Remote Token="@{env:...}"/>` reads the IRIS daemon
environment, not the shell. Set env vars at **container start**:

```bash
# CORRECT
docker run -e ATLASSIAN_API_TOKEN=... intersystems/iris:...

# WRONG — only the subprocess sees it, not the daemon
docker exec -e ATLASSIAN_API_TOKEN=... container_name ...
```

### `$Get` on an object expression, inside a fire-and-forget `Catch`

`$Get` takes a variable or an array node. On an object it raises
`<INVALID CLASS> ... Class '%Library.DynamicObject' does not support
MultiDimensional operations`:

```objectscript
// WRONG — throws on every call
Set tCallId = $Get(call.%Get("id"), "")

// CORRECT — %Get already returns "" for an absent key
Set tCallId = call.%Get("id")
```

That line sat inside `OTelAuditPolicy.%LogExecution`, wrapped in the `Catch` that
exists so a dead collector cannot break a tool call. The policy therefore emitted no
spans at all, and logged nothing about why, until a subclass was compiled whose
`Catch` reported instead of swallowing. Keep the swallow — an audit hook must not
propagate failure — but keep the body it wraps small enough to read.

### There is no `Protected` method keyword

```objectscript
// WRONG — the class will not load at all
Method EmitChatSpan(...) As %Status [ Protected ]

// CORRECT
Method EmitChatSpan(...) As %Status [ Private ]
```

ObjectScript methods are public or `Private`; `Protected` is a Java/C# habit. The class
fails to parse rather than to compile, and `$system.OBJ.Load` reports it as
`ERROR #5559: ... could not be parsed correctly, possibly due to non-matching {} or ()
characters` and then blames a `}` sixty lines lower down. That message sends you looking
for an unbalanced brace that does not exist — the braces balance exactly.

`%Compiler.UDL.TextServices.SetTextFromFile()` is the tool that answers the question.
It reports position and cause where the compiler reports neither:

```objectscript
Set sc = ##class(%Compiler.UDL.TextServices).SetTextFromFile("USER","My.Class","/tmp/My.cls")
Write $System.Status.GetErrorText(sc)
// ERROR #8500: Error: 'Unknown Keyword' in Line 99 at offset 184 (Method ... [ Protected ])
```

Reach for it on any `#5559`. Bisecting the file by hand costs an hour and points at the
wrong line, because the cascaded error looks like the real one.

### `<Policies>` entries are named for the policy kind

```xml
<Policies>
  <Authorization Class="My.RBACPolicy"/>
  <Discovery Class="My.RoleDiscovery"/>
  <Audit Class="Sample.AI.Policies.OTelAuditPolicy"/>
</Policies>
```

A `<Policies>` block the spec parser does not recognize fails silently: the class
compiles, the endpoint registers, and no policy runs.

### ConfigStore pattern

```objectscript
Set tSC = ##class(%AI.Utils.SettingStore).RegisterDefaults()
Set tJson = ##class(%AI.Utils.SettingStore).Expand("@{config:AI.LLM.MyConfig}")
Set tSettings = {}.%FromJSON(tJson)
Set tProvider = ##class(%AI.Provider).Create(tSettings.model_provider, tSettings)
Set tAgent = ##class(%AI.Agent).%New(tProvider)  // set Provider BEFORE %Init()
Set tAgent.Model = tSettings.model
Set tSC = tAgent.%Init()
```

## Setup

**ObjectScript** — import into IRIS:

```objectscript
Do $system.OBJ.ImportDir("/path/to/ai-hub/objectscript/cls", "*.cls", "ck", , 1)
```

**Python** — requires `iris_llm` wheel from IRIS distribution:

```bash
python3 -m venv .venv
.venv/bin/pip install /path/to/IRIS-*/dist/macos/iris_llm-*.whl
.venv/bin/pip install pytest pytest-asyncio anyio
```

**Run examples:**

```objectscript
Do ##class(Sample.AI.Examples.JiraAgent).Demo()
Do ##class(Sample.AI.Examples.ConfigStoreSetup).Run()
Do ##class(Sample.AI.Examples.ConfigStoreAgent).Demo()
Do ##class(Sample.AI.Examples.OTelObservability).Demo()
```

## Tests

| Suite                                         | Count | Needs                                                                         |
| --------------------------------------------- | ----- | ----------------------------------------------------------------------------- |
| `tests/unit/test_session_store.py`            | 9     | Nothing. The `iris_llm`-dependent class is `skipif`-guarded.                  |
| `tests/integration/test_oauth_rbac.py`        | 29    | `irispython` inside an AI Hub container — `$Roles` is not reachable over TCP. |
| `tests/integration/test_oauth_live_idp.py`    | 15    | A live IdP and a live MCP endpoint. Standard library only, runs on the host.  |
| `tests/integration/test_bridge_governance.py` | —     | `irispython` inside a container with the bridge classes compiled.             |
| `tests/integration/test_jira_atlassian.py`    | —     | A live Atlassian token in the **daemon** environment (see gotcha above).      |

```bash
# Local — embedded tests skip gracefully
.venv/bin/pytest tests/unit/ tests/integration/ -v

# OAuth RBAC, end to end in a throwaway container
export IRIS_IMAGE=<registry>/intersystems/iris-community:<ai-tag>
bash scripts/run-oauth-tests.sh

# OAuth RBAC against a live IdP — brings up Keycloak, then drives real tokens
(cd fixtures/keycloak && docker compose up -d --wait)
MCP_OAUTH_ENDPOINT=http://localhost:8888/mcp/sampleoauth \
    pytest tests/integration/test_oauth_live_idp.py -v

# In container (irispython)
docker exec <container> /usr/irissys/bin/irispython \
    -m pytest /path/to/tests/integration/test_bridge_governance.py -v
```

`tests/integration/MockRBACPolicy.cls` and `MockRoleDiscovery.cls` subclass the real policy
classes and override `GetCallerRoles()` so deny/allow paths can be tested deterministically
without manipulating `$Roles`. That is why the mocked half of the suite runs without an IdP.
