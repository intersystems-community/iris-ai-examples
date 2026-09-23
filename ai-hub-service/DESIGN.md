# AI Hub Service: design

A proposal, with a working prototype, for shipping IRIS AI Hub as a service
(one deployable unit with a REST contract) alongside the SDK.

- [The signal](#the-signal)
- [What "a service for agents" has to mean](#what-a-service-for-agents-has-to-mean)
- [The shape](#the-shape)
- [Deployment topologies](#deployment-topologies)
- [Meshing a legacy IRIS: the options, and the one chosen](#meshing-a-legacy-iris-the-options-and-the-one-chosen)
- [The contract](#the-contract)
- [How an IRIS application uses it](#how-an-iris-application-uses-it)
- [Governance](#governance)
- [Packaging for Kubernetes](#packaging-for-kubernetes)
- [What the prototype proves, and what it does not](#what-the-prototype-proves-and-what-it-does-not)
- [From prototype to product](#from-prototype-to-product)
- [Open questions](#open-questions)

---

## The signal

TrakCare, AI Hub's largest prospective adopter, has said the SDK is not what
it wants. It wants a service for agents.

That should be read literally before it is read charitably. An SDK assumes the
adopter will:

1. **run a new enough IRIS.** `%AI.*` exists only on 2026.2.0AI+. A product
   like TrakCare ships on a certified IRIS version per site, across many sites,
   under change control. "Upgrade first" is a multi-year programme.
2. **adopt a programming model.** `%AI.ToolSet` XData, `%AI.Agent` subclasses,
   provider config, MCP web applications with the right `Type` bit, and the
   sharp edges this repo's READMEs spend pages on (the load-bearing trailing
   slash, `Type = 18`, `@{env:}` expanding only at daemon start).
3. **own the operations.** Model credentials, provider outages, rate limits,
   prompt and tool versioning, audit, human sign-off, deployment and upgrade
   of whatever runs the agent loop.

A product team with a large ObjectScript, SQL and Interoperability codebase
wants the reverse of all three. It wants to call a capability from the code it
already has, on the IRIS it already runs, and let someone else run the moving
parts. That is what "service" means here, and the preference is reasonable.

The SDK is not wrong; it is the wrong **unit of delivery** for this customer.
It is an engine. They asked for a car.

## What "a service for agents" has to mean

Requirements, taken from the gap above and from what this repo already
learned the hard way:

| #   | Requirement                                                            | Why                                                                          |
| --- | ---------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| R1  | A versioned HTTP contract; callers write no AI code                    | The whole ask                                                                |
| R2  | Callable from any IRIS version, from ObjectScript, SQL and productions | That is where TrakCare-class logic lives                                     |
| R3  | Existing application code becomes tools **without modification**       | No one rewrites certified code to make it agent-callable                     |
| R4  | Works with an AI Hub IRIS **in place**, or **beside** a legacy one     | The installed base spans both                                                |
| R5  | Human approval is a platform feature, not a prompt instruction         | "The model was told to ask first" is not a clinical-safety case              |
| R6  | Every tool call is audited: who, what, which instance, result          | Regulated domains ask for it before anything else                            |
| R7  | Deterministic workflows alongside model-driven agents                  | Many "agent" use cases are known workflows that need the tools and the audit |
| R8  | Bring your own model, including none                                   | Data residency; some sites will never send PHI to a public endpoint          |
| R9  | One command to deploy; Kubernetes-native                               | "Service in a box"                                                           |
| R10 | AI Hub stays the engine                                                | The service productizes the SDK rather than competing with it                |

## The shape

```text
 IRIS application (any version)                    AI Hub Service                          IRIS instances
 ──────────────────────────────                    ──────────────                          ──────────────
  ObjectScript  AIHub.Client ─┐          ┌───────────────────────────────┐
  SQL           AIHub.Ask()  ─┼── HTTP ─▶│  /v1  REST contract (OpenAPI) │
  Production    AgentOperation┘  +key    ├───────────────────────────────┤
                                         │  Governance                   │
  Any other client (web UI,              │   roles · approval gate ·     │
  another service, a CHW app) ──────────▶│   audit · callback allow-list │
                                         ├───────────────────────────────┤
                                         │  Agent runtime                │
                                         │   playbook │ openai │ anthropic│
                                         │   runs park/resume (JSON state)│
                                         ├───────────────────────────────┤        ┌──────────────────────────┐
                                         │  Tool catalog = the mesh      │── MCP ─▶│ AI Hub IRIS              │
                                         │   each tool bound to the      │        │  %AI.ToolSet via         │
                                         │   instance that can answer it │        │  iris-mcp-server         │
                                         │                               │        └──────────────────────────┘
                                         │                               │        ┌──────────────────────────┐
                                         │                               │─Native▶│ Legacy IRIS (any version)│
                                         │                               │  API   │  SQL · classmethods ·    │
                                         │                               │        │  AIHub.Legacy.Interop    │
                                         └───────────────────────────────┘        └──────────────────────────┘
```

Four layers, each with one job:

**The contract.** `/v1/…`, published as [openapi.json](./openapi.json), which
a test holds equal to what the code serves. Tools, agents, runs, approvals,
audit. Nothing in it mentions IRIS versions, MCP, or which model runs.

**Governance.** Roles per principal. A `write` tool called inside a run
**parks the run** in `awaiting_approval` until a principal holding `approver`
decides. The requester cannot approve their own run. Every call lands in the
audit log with principal, run, backend and timing. Callbacks go only to hosts
the operator lists.

**The agent runtime.** Engines decide the next tool call; the runtime executes
it, applies policy and records it. All engine state is plain JSON on the run,
so a run can wait days for a clinical lead and resume with the model's context
intact. Three engines ship:

- `playbook` is a declared sequence of steps with `when:` conditions. It needs
  no model and no key, and it is deterministic. CareConnect's assessment
  workflow is one.
- `openai` covers any OpenAI-compatible endpoint (OpenAI, Azure, vLLM, Ollama).
- `anthropic` is the Messages API.

**The tool catalog.** One list of tools; each bound to a backend:

| Backend  | Talks to                                        | IRIS requirement                | Used for                                   |
| -------- | ----------------------------------------------- | ------------------------------- | ------------------------------------------ |
| `mcp`    | `iris-mcp-server` in front of `%AI.MCP.Service` | AI Hub build                    | Tools written as `%AI.ToolSet`             |
| `iris`   | The Native API: SQL, or a classmethod           | Any version with the Native API | Existing application code, unmodified (R3) |
| `python` | An in-process object or function                | None                            | Offline mode, tests, pure-Python tools     |

The catalog is where the mesh lives. That is the central design decision, and
the next two sections justify it.

## Deployment topologies

The same service image, the same agents, the same governance. A topology is
a config file that says which backend answers which tool.

| Mode         | Customer has                        | Deploys                                | Tool routing                                                          |
| ------------ | ----------------------------------- | -------------------------------------- | --------------------------------------------------------------------- |
| **in-place** | An AI Hub IRIS with its toolsets    | The service                            | Every tool → `mcp` on that instance                                   |
| **sidecar**  | A legacy IRIS they will not upgrade | The service + an AI Hub companion IRIS | Data and interop → `iris` on legacy; `%AI` logic → `mcp` on companion |
| **offline**  | Nothing yet                         | The service                            | Every tool → `python`                                                 |

For CareConnect these are [inplace.yaml](./examples/careconnect/inplace.yaml),
[sidecar.yaml](./examples/careconnect/sidecar.yaml) and
[offline.yaml](./examples/careconnect/offline.yaml). All three extend
[base.yaml](./examples/careconnect/base.yaml), which holds everything that is
a property of the application rather than of the topology: agents, policy,
and which tools are writes.

In sidecar mode:

- **Legacy IRIS** (the demo pins 2025.1) keeps `CareConnect.Patient` and
  `CareConnect.Production`. Nothing on it is upgraded. It gains one
  version-neutral class, `AIHub.Legacy.Interop`, and only because the
  interop tools need it.
- **Companion IRIS** (an AI Hub build) compiles `CareConnect.Tools.SDoHToolSet`
  unmodified and serves it over MCP. It holds logic, no data, so it is
  disposable.
- **The service** sends `FetchPatientSummary` to the legacy instance as SQL,
  `AssessSDoHRisk` to the companion over MCP, and `TriggerFollowUp` to the
  legacy production through the allow-listed dispatcher. Callers see one
  catalog.

## Meshing a legacy IRIS: the options, and the one chosen

"Mesh a legacy IRIS with a new one" has at least four readings. They are not
mutually exclusive, and a real rollout may use more than one.

| Option                         | How                                                                                   | For                                                                                                        | Against                                                                                                                                                                                                 |
| ------------------------------ | ------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A. Tool routing** (chosen)   | The service binds each tool to the instance that holds what it needs                  | No change to either IRIS's configuration; works on any Native API version; per-tool, auditable, reversible | Tools on the companion cannot see legacy data directly; a `%AI` tool that must query legacy data needs B or C, or must be split                                                                         |
| B. ECP                         | Companion as ECP application server of the legacy data server                         | `%AI` tools on the companion see legacy globals as local: zero tool changes                                | A new cross-version ECP link into a production data server is an infrastructure change the customer's DBAs own; version compatibility must be verified per pair; the blast radius is the whole database |
| C. SQL Gateway / linked tables | Companion links legacy tables over JDBC/ODBC                                          | Table-grain, read-mostly, familiar                                                                         | Per-table setup, a second copy of the schema to keep in sync, gateway latency on every query                                                                                                            |
| D. Interop over HTTP           | Legacy productions call the service (`AgentOperation`); the service calls legacy REST | Pure HTTP; any version                                                                                     | Only covers what already has an HTTP surface; it is the calling direction, not the data direction                                                                                                       |

A is the default because it is the only option that asks nothing of the
customer's database configuration, and because it fits R3: a legacy classmethod
or query becomes a tool through config, not code. B is the answer when a
`%AI`-native tool genuinely needs legacy data in-process (vector search over
legacy records, for example). The design admits it: an `mcp` tool on a
companion that is an ECP client is still just an `mcp` tool to the service.
D ships regardless, because it is how the legacy application calls agents at
all (see [How an IRIS application uses it](#how-an-iris-application-uses-it)).

This is the sharpest open technical question for a TrakCare pilot. Their data
access patterns decide whether A alone is enough.

## The contract

```text
GET  /healthz                       liveness
GET  /readyz                        every backend answers (503 otherwise)
GET  /v1/service                    mode, backends, caller's principal and roles
GET  /v1/tools                      the catalog: name, schema, effect, backend
POST /v1/tools/{tool}/invoke        one tool, no agent, no model
GET  /v1/agents                     agents, their tools, which are gated
POST /v1/agents/{agent}/runs        start a run; wait for it or poll it
GET  /v1/runs[?status=…]            own runs; approvers see all (the queue)
GET  /v1/runs/{run}                 status, output, every step, every event
POST /v1/runs/{run}/approval        approve or reject the parked call
POST /v1/runs/{run}/cancel
GET  /v1/audit                      every tool invocation
```

A run's lifecycle:

```text
running ──▶ awaiting_approval ──approve──▶ running ──▶ succeeded
   │               │                                    failed
   │               └──reject──▶ running (the tool reports REJECTED; nothing ran)
   └──▶ cancelled
```

Design choices worth defending:

- **Runs are resources, not calls.** An agent run can outlive an HTTP request
  by days, because it waits for a person. Callers that want the simple form
  pass `wait: true` and get the settled run back in one round trip. That is
  what `AIHub.SQL.Ask` does.
- **Tools return text.** That matches `%AI.ToolSet` and what models consume.
  The service does not invent a typed result layer the SDK does not have.
- **The model never sees the approval.** It sees the tool result: either the
  real output or `REJECTED by <approver>: <reason>`. Governance is not a
  prompt.

## How an IRIS application uses it

Three wrappers in [objectscript/AIHub](./objectscript/AIHub/), all of them
version-neutral. They use `%Net.HttpRequest`, `%DynamicObject` and `Ens.*`,
and never `%AI`, embedded Python or `%JSON.Adaptor`. A test enforces that.

**SQL.** For logic that lives in queries and reports:

```sql
SELECT AIHub.Ask('sdoh-assessment', '', '{"patientId":"maria-gonzalez-001"}')
SELECT AIHub.Tool('AssessSDoHRisk', '{"patientId":"p1","clinicalSummary":"lives alone, no car"}')
```

**Interoperability.** `AIHub.Interop.AgentOperation` is a business operation
on `EnsLib.HTTP.OutboundAdapter`. A business process sends an `AgentRequest`
and gets an `AgentResponse`, traced in the message viewer like any other hop.
The API key comes from an Interoperability credential, never from a message.

**ObjectScript.** `AIHub.Client` has `RunAgent`, `GetRun`, `Decide`,
`AwaitingApproval`, `InvokeTool` and `Ask`.

Going the other way, `AIHub.Legacy.Interop` lets the service drive a legacy
production. `Dispatch` builds a request object from JSON and hands it to a
business service, but only one an administrator added to an allow-list along
with its request class.

## Governance

| Control             | Prototype                                                   | Product                                                                                             |
| ------------------- | ----------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Identity            | API keys → principal + roles, from config / a Secret        | OIDC bearer tokens; roles from IdP claims (the ai-hub OAuth pattern measured this against Keycloak) |
| Approval            | `write` tools park the run; approver role; no self-approval | Per-tool approver groups, quorum, expiry, escalation                                                |
| Audit               | Per-run steps + service-wide log, in memory                 | Durable, append-only, exported (OTel `gen_ai.*` spans, as ai-hub's OTel pattern emits)              |
| Data egress         | Callbacks to allow-listed hosts only                        | Plus PHI redaction on tool output before it reaches a model (careconnect-sdoh ships `phi_guardian`) |
| Blast radius        | A tool is reachable only if listed in the agent's `tools`   | Plus per-tenant catalogs                                                                            |
| Legacy side effects | Dispatch allow-list on the legacy instance itself           | Same; it is the right place for it                                                                  |

The approval gate is enforced by the runtime, not requested of the model.
`test_engines.py` has a scripted model ask for `TriggerFollowUp` mid-batch.
The run parks, the model is not consulted again until a person decides, and
a rejected call never reaches the production.

## Packaging for Kubernetes

[deploy/k8s](./deploy/k8s/) is plain kustomize (`kubectl apply -k`), with no
chart to learn:

| Path                      | Contents                                                                                                                                     |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `base/`                   | The service: Deployment (non-root, read-only root FS, probes on `/readyz` and `/healthz`), Service, NetworkPolicy, ServiceAccount (no token) |
| `components/companion/`   | AI Hub IRIS + `iris-mcp-server` in one pod over `localhost:1972`, the same pairing careconnect-sdoh's compose makes                          |
| `components/legacy-demo/` | A stand-in legacy IRIS for demos                                                                                                             |
| `overlays/inplace/`       | base + an `ExternalName` for the existing AI Hub IRIS                                                                                        |
| `overlays/sidecar/`       | base + companion + an `ExternalName` for the existing legacy IRIS                                                                            |
| `overlays/sidecar-demo/`  | base + companion + legacy-demo: the whole proof in one namespace                                                                             |

Secrets arrive through an optional `aihub-service-secrets` Secret, whose keys
override the config's `${VAR:-default}` references. Production IRIS on
Kubernetes should use the InterSystems Kubernetes Operator (`IrisCluster`).
The companion here is a bare Deployment only because it holds no data.

## What the prototype proves, and what it does not

Proven here, with no Docker and no key (`pytest` in this directory, 116 tests):

- The contract, roles, approval park/resume/reject, no self-approval,
  visibility, cancel, audit, async runs, and the callback allow-list.
- **Topology independence.** For each of the three demo patients the same
  playbook yields the same tool sequence, tool outputs and answer offline,
  in-place and sidecar (`test_careconnect_modes.py`). The sidecar's legacy SQL
  runs for real, on SQLite, against columns read from `Patient.cls`. Its output
  matches the ObjectScript tools byte for byte through the offline port, which
  careconnect-sdoh's parity tests pin to the ObjectScript.
- MCP streamable-HTTP (JSON and event-stream replies, session ids, re-init
  after a server restart) and Native API reconnects, against fakes.
- The OpenAI and Anthropic loops, including a gated call inside a batch of
  three and a rejection reported back to the model.
- The ObjectScript contract: every path the wrappers call is a served route;
  every field they read is one a run returns; every classmethod, table,
  column and message property the sidecar binds to exists in a shipped class.
- The manifests render with `kustomize build` and validate with
  `kubeconform -strict` (22 resources across the three overlays). The Service
  selectors, ports and URLs are checked against each other.

**Not yet verified**, and it should be before anyone quotes it:

- **The ObjectScript was not compiled.** No IRIS image was pullable where
  this was built. The `AIHub.*` classes need a compile on a real legacy
  release (2023.1, 2024.1 and 2025.1 at minimum) and an end-to-end
  `AIHub.SQL.Ask` round trip.
- **No live MCP round trip** against an AI Hub `iris-mcp-server`. The client
  follows the MCP spec; the real server's quirks, if any, are unmeasured.
- **The images and the Kubernetes deployment were not run.** They were built
  as files and validated, but never started.
- **No real model** drove `sdoh-assistant`. The loops ran against scripted
  replies only.

## From prototype to product

1. **Verify the unverified list** on a kind cluster with the three images:
   the `sidecar-demo` overlay, end to end.
2. **Durable run store.** Runs and audit in memory mean one replica and
   nothing survives a restart. The natural home is IRIS globals on the
   companion: it is already there, it is IRIS, and it gives the audit trail
   IRIS's own durability and journaling. `runs.py` keeps the store behind a small interface for exactly this swap.
3. **OIDC** in place of API keys, reusing the ai-hub OAuth pattern's role
   mapping.
4. **An `iris-agent` engine** that runs a `%AI.Agent` class on the companion
   and relays its steps. That puts the SDK's own agent loop, ConfigStore
   providers and policies behind the same contract (R10).
5. **Declarative tool import**: generate the catalog entries for an existing
   class's classmethods or a schema's tables, to take the typing out of R3.
6. **OTel** spans per run and per tool call; PHI redaction before model calls.
7. **Multi-tenancy**: one service, many hospitals, per-tenant catalogs, keys
   and backends.
8. **An operator** (or IKO integration) once the shape has settled, not before.

## Open questions

These are for product and for TrakCare, not for the code:

1. **Which agents first?** The service is only as useful as the tools behind
   it. A TrakCare pilot needs two or three concrete workflows chosen with them,
   and each needs a named approver role.
2. **Where may the model run?** R8 lets a site choose, but someone has to
   decide per site whether PHI may leave for a hosted model or must stay on a
   local endpoint.
3. **Is the companion a licensed IRIS instance?** Sidecar mode doubles the
   IRIS count per site. That is a commercial question with a technical answer
   either way.
4. **Is tool routing enough, or is ECP required?** This depends on whether
   their `%AI` tools must read legacy data in-process (see the meshing
   section).
5. **Who operates it?** A customer-run Kubernetes deployment, an
   InterSystems-managed service, or both. The artifact is the same; the
   support model is not.
6. **Latency budget.** A waited-for run is seconds to minutes. Any SQL-in-a-loop
   or UI-thread use needs the async form and a callback, and product should
   say so up front.
