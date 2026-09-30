# AI Hub Service

**Agents as a service for IRIS applications.** A REST service in front of IRIS
AI Hub that combines a tool catalog, an agent runtime and a governance layer
(roles, human approval, audit), deployable to Kubernetes with one
`kubectl apply -k`. An application on any IRIS version calls it over HTTP,
from ObjectScript, SQL or an Interoperability production. It imports no SDK
and needs no upgrade.

It is proved out on [careconnect-sdoh](../careconnect-sdoh/). The same SDoH
agent runs in three topologies and gives the same answer in each:

| Mode         | What you have                             | What the service talks to                                                                                 |
| ------------ | ----------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| **offline**  | Nothing                                   | In-process port of `SDoHToolSet`                                                                          |
| **in-place** | An AI Hub IRIS (careconnect-sdoh's stack) | Its MCP endpoint, for every tool                                                                          |
| **sidecar**  | A pre-AI-Hub IRIS you will not upgrade    | That IRIS over SQL/Native API for data and interop, plus an AI Hub companion over MCP for the `%AI` logic |

**Why this exists, the alternatives weighed, and what is and is not verified
yet: [DESIGN.md](./DESIGN.md).**

## Quickstart (offline, 30 seconds, no Docker)

```bash
cd ai-hub-service
pip install -r requirements.txt
PYTHONPATH=src python -m aihub_service --config examples/careconnect/offline.yaml
```

In another terminal, start an SDoH assessment for Maria Gonzalez as a community
health worker:

```bash
curl -s -X POST localhost:8080/v1/agents/sdoh-assessment/runs \
  -H 'Authorization: Bearer dev-chw-key' -H 'Content-Type: application/json' \
  -d '{"context": {"patientId": "maria-gonzalez-001"}}' | python -m json.tool
```

Maria scores URGENT (5 of 6 domains), so the playbook wants to fire the
follow-up production, and that is a `write` tool. The run comes back
`"status": "awaiting_approval"` with the exact call it wants to make, and
nothing has fired yet. A clinical lead works the queue:

```bash
curl -s 'localhost:8080/v1/runs?status=awaiting_approval' -H 'Authorization: Bearer dev-lead-key'
curl -s -X POST localhost:8080/v1/runs/<run id>/approval \
  -H 'Authorization: Bearer dev-lead-key' -H 'Content-Type: application/json' \
  -d '{"decision": "approve", "reason": "URGENT - CHW visit this week"}'
```

The run resumes, triggers the follow-up, reads the interop traces and returns
the assessment, the care plan and the job id. Every step records the backend
that answered it and who approved it. `GET /v1/audit` (approver key) shows
every tool call the service has made. The whole contract is in
[openapi.json](./openapi.json); FastAPI also serves it live at `/docs`.

Dev keys (override with `AIHUB_KEY_*`, see [.env.example](./.env.example)):

| Key             | Principal         | Roles                        |
| --------------- | ----------------- | ---------------------------- |
| `dev-chw-key`   | `chw_user`        | caller                       |
| `dev-lead-key`  | `clinical_lead`   | caller, approver             |
| `dev-app-key`   | `careconnect_app` | caller (the IRIS app itself) |
| `dev-admin-key` | `admin`           | caller, approver, admin      |

## Agents

Both are declared in [examples/careconnect/base.yaml](./examples/careconnect/base.yaml):

- **`sdoh-assessment`** is a **playbook**, with no model and no key. It runs
  FetchPatientSummary, SearchSDoHProtocols, AssessSDoHRisk and DraftCarePlan.
  It calls TriggerFollowUp when the case is URGENT or `context.followUp` is set,
  and that call is gated. GetInteropTraces runs once a follow-up has actually
  fired. Requires `context.patientId`.
- **`sdoh-decision-gate`** uses Liquid AI `d1:free` through the Decision API. It
  asks a typed Choice for the action, a Score for urgency, and a Noul for consent;
  d1 returns calibrated probabilities with zero output tokens. The default
  `LIQUID_DECISION_MODE=mock` keeps local tests keyless. Set
  `LIQUID_DECISION_MODE=liquid` and `LIQUID_API_KEY=liquid_...` to call Liquid.
  `TriggerFollowUp` remains a separate approval-gated write.
- **`sdoh-assistant`** is **model-driven** over the same tools. Set
  `AIHUB_LLM_ENGINE` (`openai` or `anthropic`), `AIHUB_LLM_MODEL` and
  `AIHUB_LLM_API_KEY`. For a local model, use `AIHUB_LLM_BASE_URL` with any
  OpenAI-compatible endpoint. The approval gate applies to it exactly as to the
  playbook, because the runtime enforces it, not the prompt.

## Running the other modes

```bash
# in-place: in front of careconnect-sdoh's own AI Hub stack
(cd ../careconnect-sdoh && make up)
docker compose --profile inplace up -d --build

# sidecar: a 2025.3 IRIS holding the data + production, an AI Hub companion,
# and the service meshing them. The companion needs an AI Hub image
# (IRIS_IMAGE, see ../careconnect-sdoh/docs/eap-setup.md).
docker compose --profile sidecar up -d --build
```

Every mode answers on `localhost:${AIHUB_PORT:-8080}`. Containers are named
`ai-hub-service-*` and every host port is overridable.

## Kubernetes

```bash
# images (from the repo root)
docker build -f ai-hub-service/Dockerfile -t aihub-service:0.1.0 .
docker build -f ai-hub-service/docker/legacy-iris/Dockerfile -t ai-hub-service-legacy-iris:0.1.0 .
docker build -f careconnect-sdoh/services/iris-ai-hub/Dockerfile \
  --build-arg IMAGE=$IRIS_IMAGE -t ai-hub-service-companion-iris:0.1.0 careconnect-sdoh

# the whole sidecar proof in one namespace
kubectl create namespace careconnect-demo
kubectl apply -k ai-hub-service/deploy/k8s/overlays/sidecar-demo -n careconnect-demo
```

| Overlay        | For                                                                                        |
| -------------- | ------------------------------------------------------------------------------------------ |
| `inplace`      | An existing AI Hub IRIS: point `existing-iris.yaml`'s `externalName` at it                 |
| `sidecar`      | An existing legacy IRIS: point `legacy-iris.yaml` at it; the companion is deployed for you |
| `sidecar-demo` | Everything, with a demo legacy IRIS carrying CareConnect's data                            |

Real credentials go in a Secret named `aihub-service-secrets`. Its keys (for
example `AIHUB_KEY_APP`, `AIHUB_LLM_API_KEY`, or `LIQUID_API_KEY`) override the
config's defaults.

## From an IRIS application

Load [objectscript/AIHub](./objectscript/AIHub/) into the application's
namespace. The classes are version-neutral: no `%AI`, no embedded Python.

```objectscript
Do ##class(AIHub.Client).Configure("aihub-service", 8080, "dev-app-key")
```

**From SQL:**

```sql
SELECT AIHub.Ask('sdoh-assessment', '', '{"patientId":"maria-gonzalez-001"}')
SELECT AIHub.Tool('AssessSDoHRisk', '{"patientId":"p1","clinicalSummary":"lives alone"}')
```

`Ask` returns the output, or a line starting `AWAITING_APPROVAL <run id>:` or
`ERROR:`. `AIHub.RunStatus(id)` and `AIHub.RunOutput(id)` follow up.

**From a production:** add `AIHub.Interop.AgentOperation`, send it an
`AIHub.Interop.AgentRequest`, and get back an `AIHub.Interop.AgentResponse`.
The class comment has the `<Item>` XML. The key comes from an
Interoperability credential.

**From ObjectScript:**

```objectscript
Set client = ##class(AIHub.Client).FromConfig()
Set sc = client.RunAgent("sdoh-assessment", "", {"patientId": "james-okafor-002"}, 1, .run)
Write run.status, !, run.output, !
```

**Letting the service drive a legacy production** (sidecar mode): load
`AIHub.Legacy.Interop` and allow-list each business service it may call:

```objectscript
Do ##class(AIHub.Legacy.Interop).Allow("CareConnect.Service.SDoHFollowUpBS", "CareConnect.Message.FollowUpRequest")
```

## Making your own application a service

Write a config: see [sidecar.yaml](./examples/careconnect/sidecar.yaml) for
every binding shape.

- **An existing SQL query becomes a tool**: `binding: {sql: ..., params: [...]}`.
- **An existing classmethod becomes a tool**:
  `binding: {classmethod: Pkg.Class.Method, args: [...]}`.
- **An existing `%AI.ToolSet`**: `backend: <an mcp backend>`. The schema comes
  from the server. Set the backend's `tool_prefix` to the web application's
  prefix: iris-mcp-server publishes `/mcp/careconnect` tools as
  `mcp_careconnect_<Tool>`, and `/readyz` fails if a bound tool is not listed.
- **A known workflow becomes an agent**: `engine: playbook` with `steps:`. A
  step whose tool answers `ERROR` fails the run.
- **A side effect**: `effect: write`, and the approval gate applies.

## Layout

```text
src/aihub_service/      the service: app (HTTP), catalog, backends/, engines/, runs, policy
examples/careconnect/   base + offline/inplace/sidecar configs; formatters for the legacy route
objectscript/AIHub/     the IRIS-side wrappers (Client, SQL, Interop.*, Legacy.Interop)
deploy/k8s/             kustomize base, components, overlays
docker/legacy-iris/     the demo's pre-AI-Hub IRIS image
tests/                  116 tests, no Docker, no IRIS, no key
openapi.json            the contract, held current by a test
```

## Tests

```bash
cd ai-hub-service && python -m pytest
```

With `kustomize` on `PATH`, three more tests build the overlays for real.
[DESIGN.md](./DESIGN.md#what-the-prototype-proves-and-what-it-does-not) lists
exactly what the suite covers and what still needs a live IRIS.
