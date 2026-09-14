# IRIS AI Hub EAP Setup

The CareConnect demo uses **IRIS AI Hub** — the `%AI.*` class library that
provides `%AI.ToolSet`, `%AI.Agent`, `%AI.MCP.Service`, and related primitives.

AI Hub is currently in Early Access. Without the EAP image, the stack still
builds and the FHIR server, Python app, and knowledge graph (IVG) all work —
but the MCP tool endpoint and agent logic require the EAP build.

## Step 1 — Sign up for the EAP

Go to the EAP repo and follow the enrollment instructions:

> **<https://github.com/intersystems-community/ai-hub-eap>**

You'll receive access to a tarball (`.tar` file) containing the IRIS AI Hub
Docker image.

## Step 2 — Load the image

```bash
docker load < irishealth-ai-hub-2026.x.x.tar
```

Note the image tag that prints after loading — it will include the full registry
path embedded in the tarball, e.g.:

```text
Loaded image: <registry>/intersystems/irishealth:2026.3.0AI.139.0
```

## Step 3 — Set IRIS_IMAGE in .env

```bash
cp .env.example .env
```

Edit `.env`:

```dotenv
IRIS_IMAGE=<registry>/intersystems/irishealth:2026.3.0AI.139.0
```

Replace the tag with whatever your tarball produced.

## Step 3b — Get the iris-mcp-server binary (for stdio transport)

The `iris-mcp-server` binary in the repo is Linux ARM64 only. To get a native
binary for your platform, extract it from the loaded image:

```bash
# Create a temporary container, copy the binary, remove the container
docker create --name tmp-hub $IRIS_IMAGE
docker cp tmp-hub:/usr/irissys/bin/iris-mcp-server ./iris-mcp-server
docker rm tmp-hub
chmod +x ./iris-mcp-server
```

Then reference the extracted binary in your MCP client config.

## Step 4 — Start the stack

```bash
docker compose up -d --wait
```

Or with the IVG knowledge graph:

```bash
docker compose --profile ivg up -d --wait
```

## Without the EAP

If you don't have EAP access yet, the stack still runs with `intersystemsdc/irishealth-community:2026.2`
(the default). You can:

- Run all unit tests: `make test-unit`
- Run IVG knowledge graph tests: `make test-ivg`
- Explore the FHIR data layer and Python agents
- Read the ObjectScript source in `src/CareConnect/`

The features that require the EAP image: MCP tool endpoint (`/mcp/careconnect`),
`%AI.ToolSet`-based tool dispatch, and the `SDoHAssessment` agent class.

## Reference

- EAP repo and docs: <https://github.com/intersystems-community/ai-hub-eap>
- MCP Server Guide: <https://github.com/intersystems-community/ai-hub-eap/blob/master/MCP_Server_Guide.md>
- Community forum: <https://community.intersystems.com>
