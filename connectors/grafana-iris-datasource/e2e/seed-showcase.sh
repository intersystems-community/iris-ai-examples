#!/usr/bin/env bash
# Loads the synthetic showcase dataset for e2e/grafana/dashboards/iris-showcase.json: two Tenants, three IRIS
# instances each, 48 hours of deploys (each with a revision id), findings, Episodes and 5-minute log-storm rollups,
# ending now. Time columns are epoch milliseconds, as an event store keeps them. Nothing in it is real: the shape
# follows an operations-review event store, the content comes from a seeded random generator, so every run makes
# the same data, shifted to end at the time it runs. Safe to run again: it drops and recreates the tables.
set -euo pipefail
URL="${IRIS_URL:-http://localhost:33273}" USER_="${IRIS_USER:-_SYSTEM}" PASS="${IRIS_PASSWORD:-SYS}"

python3 - "$URL" "$USER_" "$PASS" <<'PY'
import base64, json, random, sys, time, urllib.request

url, user, pw = sys.argv[1:4]
auth = base64.b64encode(f"{user}:{pw}".encode()).decode()

def run(sql, ok_to_fail=False):
    r = urllib.request.Request(f"{url}/api/atelier/v1/USER/action/query", json.dumps({"query": sql, "parameters": []}).encode(),
                               {"Content-Type": "application/json", "Authorization": f"Basic {auth}"})
    d = json.load(urllib.request.urlopen(r, timeout=30))
    if d["status"]["errors"] and not ok_to_fail:
        sys.exit(f"{sql}: {d['status']['errors']}")

for table in ("Demo.Events", "Demo.Episodes", "Demo.LogRollups"):
    run(f"DROP TABLE {table}", ok_to_fail=True)
run("""CREATE TABLE Demo.Events (
  EventId VARCHAR(128) PRIMARY KEY, Ts BIGINT NOT NULL, TenantID VARCHAR(64) NOT NULL,
  InstanceID VARCHAR(128), Category VARCHAR(32), EventType VARCHAR(128), Severity VARCHAR(8),
  Title VARCHAR(512), RevisionId VARCHAR(64))""")
run("CREATE INDEX EvByInst ON Demo.Events (TenantID, InstanceID, Ts)")
run("""CREATE TABLE Demo.Episodes (
  EpisodeId VARCHAR(64) PRIMARY KEY, TenantID VARCHAR(64) NOT NULL, InstanceID VARCHAR(128),
  StartTs BIGINT NOT NULL, EndTs BIGINT, Metric VARCHAR(128), Summary VARCHAR(512))""")
run("""CREATE TABLE Demo.LogRollups (
  RollupId VARCHAR(256) PRIMARY KEY, TenantID VARCHAR(64) NOT NULL, InstanceID VARCHAR(128),
  TemplateText VARCHAR(512), BucketStart BIGINT NOT NULL, "Count" INTEGER, FirstTs BIGINT, LastTs BIGINT)""")

rng = random.Random(56)
H = 3_600_000
T0 = (int(time.time() * 1000) - 48 * H) // 300_000 * 300_000  # 48 hours ago, on a 5-minute boundary
tpls = ["ECP connection <num> lost to <ip>", "Write daemon stalled for <num> seconds",
        "Journal file <path> is <num>% full"]

def q(v):
    if v is None:
        return "NULL"
    if isinstance(v, int):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"

n = 0
for t in ("acme", "globex"):
    for i in range(3):
        inst = f"iris-{i:02d}"
        for d in range(4):  # deploys, each with a revision
            ts = T0 + rng.randrange(48 * H)
            run(f"INSERT INTO Demo.Events VALUES ({q(f'{t}-{inst}-dep{d}')},{ts},{q(t)},{q(inst)},'sal_lifecycle','sal_lifecycle.deploy','P3',{q(f'deploy app 4.2.{d}')},{q(f'rev-{t}-{i}-{d}')})"); n += 1
            if rng.random() < 0.5:  # a finding a few minutes after some deploys, and the Episode it opens
                f = ts + rng.randrange(2, 20) * 60_000
                run(f"INSERT INTO Demo.Events VALUES ({q(f'{t}-{inst}-f{d}')},{f},{q(t)},{q(inst)},'finding','mgstat.WDQsz','P2','WDQsz above 10000',NULL)")
                run(f"INSERT INTO Demo.Episodes VALUES ({q(f'ep-{t}-{i}-{d}')},{q(t)},{q(inst)},{f},{f + rng.randrange(20, 120) * 60_000},'mgstat.WDQsz','write daemon queue rose after deploy')")
                n += 2
        for b in range(48 * 12):  # 5-minute buckets; sparse log storms
            if rng.random() < 0.08:
                bs = T0 + b * 300_000
                c = rng.choice([1, 3, 40, 900])
                run(f"INSERT INTO Demo.LogRollups VALUES ({q(f'logroll:{t}:{inst}:{b}')},{q(t)},{q(inst)},{q(rng.choice(tpls))},{bs},{c},{bs + 1000},{bs + 290_000})"); n += 1
print(f"seeded {n} rows ending now")
PY
