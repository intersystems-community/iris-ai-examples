# Fix: Docker Build and MCP Connection Failures (Fresh Clone)

**Date:** 2026-05-14  
**Source:** Fresh-clone smoke test of both examples  
**Status:** Fixes ready to implement

---

## Summary

Both examples fail to build and/or connect from a fresh `git clone`. Six discrete failures were found.

---

## Failures

### F1 — careconnect-sdoh Dockerfile: COPY paths invalid

**Severity:** BLOCKER — `docker compose up` fails immediately  
**File:** `careconnect-sdoh/docker/Dockerfile`  
**Observed error:**
```
COPY --chown=... iris.script /home/irisowner/irisdev/iris.script
→ "/iris.script": not found

COPY --chown=... ../src/CareConnect /src/CareConnect
→ "/src/CareConnect": not found
```

**Root cause:**  
- Build context is `..` (i.e. `careconnect-sdoh/`). `iris.script` is at `docker/iris.script` relative to that context, not at root.  
- `../src/CareConnect` escapes the build context — Docker forbids this. No `src/CareConnect` directory exists; classes are at root level (`Tools/`, `Agent/`, `Patient.cls`, etc.).

**Fix:**  
1. Change `COPY iris.script` → `COPY docker/iris.script`  
2. Either:
   - Move all `.cls` files into a `src/CareConnect/` subdirectory (matches `iris.script` `LoadDir("/src/CareConnect")`), OR  
   - Change `COPY ../src/CareConnect /src/CareConnect` → `COPY . /src/CareConnect` (copies entire context into image at that path, filtering by what `LoadDir` processes)  
   
   **Recommended:** Move `.cls` files into `src/CareConnect/` — matches the intended layout and the iris.script LoadDir call.

---

### F2 — careconnect-sdoh docker-compose: mcp `--iris-port` set to 52773

**Severity:** BLOCKER — MCP sidecar hangs, never connects  
**File:** `careconnect-sdoh/docker/docker-compose.yml`  
**Observed:** `--iris-port 52773` → wgproto returns "early eof", server never becomes ready

**Root cause:**  
`iris-mcp-server run --iris-port` expects the IRIS **superserver port (1972)**, not the web server port (52773). The help text says "web server port" but empirically confirmed: the wgproto connection requires port 1972.

**Fix:** Change `--iris-port 52773` → `--iris-port 1972` in the `mcp` service command.

**Note:** The healthcheck on the `iris` service should remain on port 52773 (web server, correct for IRIS health check).

---

### F3 — kg-ticket-resolver docker-compose: mcp `--iris-port` set to 52773

**Severity:** BLOCKER — MCP sidecar hangs with "early eof" after ~5s  
**File:** `kg-ticket-resolver/docker/docker-compose.yml`  
**Observed:** `--iris-port 52773` → `WgProto error: I/O error: early eof`

**Root cause:** Same as F2. `iris-mcp-server run` uses wgproto over the superserver port (1972).

**Fix:** Change `--iris-port 52773` → `--iris-port 1972` in the `mcp` service command.

---

### F4 — kg-ticket-resolver README: Claude Desktop config shows wrong port

**Severity:** HIGH — Users who follow the README exactly will get a non-working MCP client  
**File:** `kg-ticket-resolver/README.md`  
**Observed:** JSON snippet shows `"--iris-port", "52773"`

**Fix:** Change `"--iris-port", "52773"` → `"--iris-port", "1972"` in the Claude Desktop config snippet.

---

### F5 — careconnect-sdoh README: Claude Desktop config shows wrong port

**Severity:** HIGH — Same issue as F4  
**File:** `careconnect-sdoh/README.md`  
**Observed:** JSON snippet shows `"--iris-port", "52773"`

**Fix:** Change `"--iris-port", "52773"` → `"--iris-port", "1972"` in the Claude Desktop config snippet.

---

### F6 — kg-ticket-resolver iris.script: misleading "Tools: N" log message

**Severity:** LOW — Cosmetic confusion only; `N` is ToolSet registrations, not individual tools  
**File:** `kg-ticket-resolver/docker/iris.script`  
**Observed:** Build outputs `KGTicketResolver ready. Tools: 5` — SEs may think one tool is missing

**Fix:** Change log message to `write "KGTicketResolver ready. ToolSet registered: KGTicketResolver.Tools.ToolSet",!`

---

## Files to Change

| File | Changes |
|------|---------|
| `careconnect-sdoh/docker/Dockerfile` | Fix COPY paths (F1) |
| `careconnect-sdoh/src/CareConnect/` | Create directory, move .cls files here (F1) |
| `careconnect-sdoh/docker/docker-compose.yml` | --iris-port 1972 in mcp command (F2) |
| `careconnect-sdoh/README.md` | --iris-port 1972 in Claude Desktop snippet (F5) |
| `kg-ticket-resolver/docker/docker-compose.yml` | --iris-port 1972 in mcp command (F3) |
| `kg-ticket-resolver/README.md` | --iris-port 1972 in Claude Desktop snippet (F4) |
| `kg-ticket-resolver/docker/iris.script` | Fix log message (F6) |

---

## Acceptance Criteria

1. `docker compose up -d` in `careconnect-sdoh/docker/` completes without error from a fresh clone
2. `docker logs careconnect-mcp` shows `Connected to IRIS at localhost:1972 with pool size 10`
3. `docker compose up -d` in `kg-ticket-resolver/docker/` completes without error from a fresh clone  
4. `docker logs kgtickets-mcp` shows `Connected to IRIS at localhost:1972 with pool size 10`
5. MCP stdio test lists 6 KGTicketResolver tools
6. Build log says `KGTicketResolver ready. ToolSet registered: KGTicketResolver.Tools.ToolSet`
