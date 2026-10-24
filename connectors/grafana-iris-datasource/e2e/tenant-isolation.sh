#!/usr/bin/env bash
# Tenant isolation through a real Grafana: a viewer in one Tenant's org sees none of another Tenant's rows on a
# shared IRIS. Needs the e2e IRIS and a Grafana running the built plugin (see docker-compose.grafana.yaml), and
# exits non-zero on the first broken promise. Safe to run again.
#
#   ./e2e/tenant-isolation.sh                                   # Grafana on :33000
#   GRAFANA_URL=http://localhost:33001 ./e2e/tenant-isolation.sh
#   TENANT_TRANSPORT=rest ./e2e/tenant-isolation.sh             # the control: REST must FAIL this
#
# What it builds. In IRIS: TenantDemo.Events holding two Tenants' rows, a view per Tenant, and an IRIS user per
# Tenant granted SELECT on its own view only (plus %Developer, which /api/atelier needs to log in at all). In
# Grafana: an org per Tenant, holding a web-terminal data source that logs in as that Tenant's IRIS user, and a
# Viewer. Grafana OSS has no per-data-source permissions, so the org is the boundary; IRIS's SQL privileges are
# what stop a viewer who writes their own SQL against /api/ds/query.
set -euo pipefail
export IRIS_URL="${IRIS_URL:-http://localhost:33273}" IRIS_USER="${IRIS_USER:-_SYSTEM}" IRIS_PASSWORD="${IRIS_PASSWORD:-SYS}"
export GRAFANA_URL="${GRAFANA_URL:-http://localhost:33000}" GRAFANA_ADMIN="${GRAFANA_ADMIN:-admin:admin}"
export TENANT_TRANSPORT="${TENANT_TRANSPORT:-terminal}"
# How Grafana's container reaches the e2e IRIS.
export IRIS_HOST_FROM_GRAFANA="${IRIS_HOST_FROM_GRAFANA:-host.docker.internal}" IRIS_PORT_FROM_GRAFANA="${IRIS_PORT_FROM_GRAFANA:-33273}"

python3 - <<'PY'
import base64, json, os, sys, time, urllib.error, urllib.request

E = os.environ
TENANTS = {"acme": [("deploy", 1), ("restart", 2)], "globex": [("deploy", 3)]}
PW = "tenant-demo-pw"

def call(method, url, auth, body=None, org=None):
    headers = {"Content-Type": "application/json", "Authorization": "Basic " + base64.b64encode(auth.encode()).decode()}
    if org:
        headers["X-Grafana-Org-Id"] = str(org)
    req = urllib.request.Request(url, json.dumps(body).encode() if body is not None else None, headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")

def iris(sql, ok_to_fail=False):
    status, d = call("POST", f"{E['IRIS_URL']}/api/atelier/v1/USER/action/query", f"{E['IRIS_USER']}:{E['IRIS_PASSWORD']}", {"query": sql, "parameters": []})
    if (status != 200 or d["status"]["errors"]) and not ok_to_fail:
        sys.exit(f"IRIS refused {sql}: {d}")

def grafana(method, path, body=None, org=None, auth=None):
    return call(method, E["GRAFANA_URL"] + path, auth or E["GRAFANA_ADMIN"], body, org)

def fail(msg):
    sys.exit("FAIL: " + msg)

# IRIS: one table, a view and a user per Tenant.
for t in TENANTS:
    iris(f"DROP VIEW TenantDemo.{t.title()}Events", True)
    iris(f"DROP USER grafana_{t}", True)
iris("DROP TABLE TenantDemo.Events", True)
iris("CREATE TABLE TenantDemo.Events (TenantID VARCHAR(20), Kind VARCHAR(20), V INT)")
for t, rows in TENANTS.items():
    for kind, v in rows:
        iris(f"INSERT INTO TenantDemo.Events VALUES ('{t}', '{kind}', {v})")
    iris(f"CREATE VIEW TenantDemo.{t.title()}Events AS SELECT TenantID, Kind, V FROM TenantDemo.Events WHERE TenantID = '{t}'")
    iris(f"CREATE USER grafana_{t} IDENTIFY BY '{PW}'")
    iris(f"GRANT SELECT ON TenantDemo.{t.title()}Events TO grafana_{t}")
    iris(f"GRANT %Developer TO grafana_{t}")

# Grafana: an org, a data source and a viewer per Tenant.
orgs, replaced = {}, False
for t in TENANTS:
    name = f"Tenant {t.title()}"
    status, org = grafana("GET", f"/api/orgs/name/{urllib.request.quote(name)}")
    if status == 200:
        org_id = org["id"]
    else:
        status, org = grafana("POST", "/api/orgs", {"name": name})
        if status != 200:
            fail(f"creating org {name}: {status} {org}")
        org_id = org["orgId"]
    orgs[t] = org_id
    grafana("POST", f"/api/orgs/{org_id}/users", {"loginOrEmail": "admin", "role": "Admin"})
    json_data = {"host": E["IRIS_HOST_FROM_GRAFANA"], "webPort": int(E["IRIS_PORT_FROM_GRAFANA"]), "namespace": "USER",
                 "username": f"grafana_{t}", "transport": E["TENANT_TRANSPORT"]}
    status, existing = grafana("GET", f"/api/datasources/uid/iris-{t}", org=org_id)
    if status != 200 or existing.get("jsonData") != json_data:
        grafana("DELETE", f"/api/datasources/uid/iris-{t}", org=org_id)
        status, ds = grafana("POST", "/api/datasources", {
            "name": "IRIS", "uid": f"iris-{t}", "type": "intersystems-iris-datasource", "access": "proxy",
            "jsonData": json_data, "secureJsonData": {"password": PW},
        }, org=org_id)
        if status != 200:
            fail(f"creating the {t} data source: {status} {ds}")
        replaced = True
    status, found = grafana("GET", f"/api/users/lookup?loginOrEmail=viewer-{t}")
    if status == 200:
        grafana("DELETE", f"/api/admin/users/{found['id']}")
    status, user = grafana("POST", "/api/admin/users", {"name": f"Viewer {t}", "login": f"viewer-{t}", "password": PW, "OrgId": org_id})
    if status != 200:
        fail(f"creating viewer-{t}: {status} {user}")
    # Grafana may also have put the new user in the main org; a Tenant viewer belongs to its Tenant's org only.
    grafana("DELETE", f"/api/orgs/1/users/{user['id']}")

# Grafana caches a data source's settings by uid for a few seconds, so a replaced one answers with its old
# settings until that runs out.
if replaced:
    time.sleep(6)
for t, org_id in orgs.items():
    status, health = grafana("GET", f"/api/datasources/uid/iris-{t}/health", org=org_id)
    if status != 200 or health.get("status") != "OK":
        fail(f"the {t} data source health check: {status} {health}")

def query(viewer, uid, sql):
    return grafana("POST", "/api/ds/query", {
        "from": "now-1h", "to": "now",
        "queries": [{"refId": "A", "datasource": {"uid": uid}, "queryText": sql, "format": "table"}],
    }, auth=f"viewer-{viewer}:{PW}")

def result_a(d):
    return (d or {}).get("results", {}).get("A", {})

checks = 0
for t in TENANTS:
    others = [o for o in TENANTS if o != t]
    status, orgs_seen = grafana("GET", "/api/user/orgs", auth=f"viewer-{t}:{PW}")
    if [o["orgId"] for o in orgs_seen] != [orgs[t]]:
        fail(f"viewer-{t} belongs to orgs {orgs_seen}, want only {orgs[t]}")
    checks += 1

    status, d = query(t, f"iris-{t}", f"SELECT TenantID, Kind FROM TenantDemo.{t.title()}Events")
    frame = result_a(d)
    if status != 200 or frame.get("error"):
        fail(f"viewer-{t} reading its own view: {status} {d}")
    tenants_seen = frame["frames"][0]["data"]["values"][0]
    if not tenants_seen or set(tenants_seen) != {t}:
        fail(f"viewer-{t} saw Tenants {tenants_seen}")
    checks += 1

    for sql in [f"SELECT * FROM TenantDemo.{o.title()}Events" for o in others] + ["SELECT * FROM TenantDemo.Events"]:
        status, d = query(t, f"iris-{t}", sql)
        err = result_a(d).get("error", "")
        if "not privileged" not in err:
            fail(f"viewer-{t} ran {sql!r} and was not refused by IRIS: {status} {d}")
        checks += 1

    for o in others:
        status, d = query(t, f"iris-{o}", f"SELECT * FROM TenantDemo.{o.title()}Events")
        frames = result_a(d).get("frames")
        if status == 200 and frames:
            fail(f"viewer-{t} queried {o}'s data source: {d}")
        checks += 1

status, health = grafana("GET", "/api/health")
print(f"tenant isolation holds on Grafana {health.get('version')}: {checks} checks passed")
PY
