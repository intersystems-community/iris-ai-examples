# AI Hub OTel demo

One web page, two chat tabs, one Langfuse. Each tab answers patient questions
by calling a tool that goes through an IRIS interoperability production, and
each reply links to its trace in Langfuse.

- **%AI.Agent**: ObjectScript `%AI.Agent`, with the loop run by the Rust core
  inside IRIS. Its tool, `Demo.AIHub.PatientTools.LookupPatient`, goes
  `ToolService` → `LookupBP` → `LookupBO`.
- **iris_llm + LangChain**: Python `ChatIris` with a small tool-calling loop.
  Its `lookup_patient` tool calls `Demo.AIHub.Chat.Lookup` over the native API,
  which runs the same production.

Both tabs produce one connected trace per turn:

```text
chat turn (%AI.Agent)                    app, FastAPI
└─ invoke_agent %AI.Agent                Rust, inside IRIS
   ├─ chat qwen3.8:27b                   Rust, token usage attached
   ├─ LookupPatient                      Rust execute_tool span
   │  └─ bs.ToolService                  IRIS interop, parented on execute_tool
   │     └─ bp.LookupBP
   │        └─ bo.LookupBO
   └─ chat qwen3.8:27b
```

The LangChain tab has the same shape, with `invoke_agent iris-langchain` and
`lookup_patient` emitted by the app. Each tab keeps its own Langfuse session,
so a conversation shows up as one session with a trace per turn.

## What it needs from the AI Hub build

The stack uses a patched AI Hub build on top of an IRIS for Health AI image:

- `irisllm.so` and the `%AI` classes from the same ai-core commit. The classes
  are loaded into IRISLIB at image build time.
- The `iris_llm` wheel from that commit, installed in the app image.
- `%AI.System.Configure("telemetry:context", ...)` and
  `%AI.Tool.CurrentTraceparent()`. These are what parent the Rust spans on the
  app's span, and the interop spans on `execute_tool`. Stock builds don't have
  them, and without them each layer starts its own trace.

## Run it

1. Stage the build and write `.env`. The script writes `.env` once, mode 600,
   with random Langfuse keys and passwords.

   ```sh
   AI_CORE_BUILD=<dir with irisllm.so and iris_llm-*.whl> \
   AI_CORE_CLS=<ai-core checkout>/iris-llm/cls \
   IRIS_IMAGE=<registry>/intersystems/irishealth:2026.3.0AI.154.0 \
   IRIS_KEY_FILE=<path to iris.key> \
   LANGFUSE_PUBLIC_URL=http://<host>:3300 \
   OPENAI_API_KEY=... \
   ./stage.sh
   ```

   On a host with no route to OpenAI, replace `OPENAI_API_KEY` with
   `LOCAL_LLM=qwen3.8:27b`. That turns on the `local-llm` compose profile, an
   Ollama container on the host GPU, and points both tabs at its
   OpenAI-compatible endpoint.

2. Start the stack. With `LOCAL_LLM`, pull the model once.

   ```sh
   docker compose up -d --build
   docker compose exec ollama ollama pull qwen3.8:27b   # LOCAL_LLM only
   ```

3. Open the app at `http://<host>:8095` and Langfuse at `http://<host>:3300`.
   The Langfuse login is `LANGFUSE_INIT_USER_EMAIL` and
   `LANGFUSE_INIT_USER_PASSWORD` from `.env`.

Ask either tab about patient 42, 7 or 13, then follow the "trace in Langfuse"
link under the reply.

| Port  | Service  | Override        |
| ----- | -------- | --------------- |
| 8095  | app      | `APP_PORT`      |
| 3300  | Langfuse | `LANGFUSE_PORT` |
| 21980 | IRIS     | `IRIS_PORT`     |

## Model settings

`DEMO_MODEL` and `DEMO_LLM_BASE_URL` configure both tabs. Unset, both use
OpenAI `gpt-4o-mini`. `Demo.AIHub.Chat` reads the same variables as
`demo_app/llm_config.py`.

Small local models need two things to call the tool reliably. The tool list
has to be short and plainly described, which is why `Interop` and `RunLookup`
are `[ Internal ]` and the kernel-bug note lives in a code comment instead of
the doc comment. The %AI.Agent tab also runs at temperature 0.2
(`Demo.AIHub.Chat` `TEMPERATURE`). At the default temperature, qwen2.5:14b
skipped the tool on 2 of 10 identical requests. At 0.2 it called it 10 of 10.
qwen3.8:27b, the model the local profile now suggests, called it 10 of 10 at
both temperatures. Its reasoning comes back in a separate `reasoning` field,
so it stays out of the reply.

## Why the tool runs in a worker job

`LookupPatient` hands the work to a `JOB` and waits for the result. Calling
`%Trace` inside an `%AI.Agent` tool callback nests a second `$ZF` call inside
the first, and the kernel's `zfpop()` doesn't restore the outer call's
argument and heap pointers. The worker gets its own process, so the interop
spans run outside the callback. It passes the `execute_tool` span's
traceparent through `^IRIS.Temp.MsgTraceparent($Job)`.

## Collector

`collector/config.yaml` forwards OTLP to Langfuse. It also rewrites the
resource attributes that the IRIS OTel library sends as booleans, which
Langfuse rejects.

## Tests

```sh
python -m venv .venv && .venv/bin/pip install fastapi httpx python-multipart \
  opentelemetry-sdk opentelemetry-exporter-otlp-proto-http langchain-core pytest
.venv/bin/pytest -q                      # unit tests, no stack needed
```

The e2e test posts to both tabs and reads each trace back from Langfuse:

```sh
DEMO_APP_URL=http://<host>:8095 LANGFUSE_URL=http://<host>:3300 \
LANGFUSE_INIT_PROJECT_PUBLIC_KEY=... LANGFUSE_INIT_PROJECT_SECRET_KEY=... \
.venv/bin/pytest -q tests/e2e
```

Langfuse v4 serves observations only from `/api/public/v2/observations`. It
types gen_ai spans as `AGENT`, `GENERATION` and `TOOL`, and names a `TOOL`
observation after the tool, so the test matches on type and name prefix.
