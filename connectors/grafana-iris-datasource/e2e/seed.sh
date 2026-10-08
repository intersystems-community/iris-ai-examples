#!/usr/bin/env bash
# Fills the e2e IRIS with six hours of two hosts' CPU and request counts, ending now, so the demo
# dashboard has something to draw. Safe to run again: it drops and recreates the table.
set -euo pipefail
URL="${IRIS_URL:-http://localhost:33273}" USER_="${IRIS_USER:-_SYSTEM}" PASS="${IRIS_PASSWORD:-SYS}"

q() {
	curl -s -m 30 -u "$USER_:$PASS" -H 'Content-Type: application/json' -X POST \
		"$URL/api/atelier/v1/USER/action/query" -d "$1" |
		python3 -c 'import sys,json; d=json.load(sys.stdin); e=d["status"]["errors"]; sys.exit(print(e[0]["error"]) or 1) if e else None'
}

q '{"query":"DROP TABLE Demo_Metrics","parameters":[]}' 2>/dev/null || true
q '{"query":"CREATE TABLE Demo_Metrics (tp TIMESTAMP, host VARCHAR(20), cpu DOUBLE, requests INT)","parameters":[]}'

python3 - "$URL" "$USER_" "$PASS" <<'PY'
import json, math, sys, urllib.request, base64, datetime
url, user, pw = sys.argv[1:4]
auth = base64.b64encode(f"{user}:{pw}".encode()).decode()
now = datetime.datetime.now(datetime.timezone.utc).replace(second=0, microsecond=0)
def run(sql):
    r = urllib.request.Request(f"{url}/api/atelier/v1/USER/action/query", json.dumps({"query": sql, "parameters": []}).encode(),
                               {"Content-Type": "application/json", "Authorization": f"Basic {auth}"})
    d = json.load(urllib.request.urlopen(r, timeout=30))
    assert not d["status"]["errors"], d["status"]["errors"]
n = 0
for step in range(72, -1, -1):                      # every 5 minutes for 6 hours
    t = now - datetime.timedelta(minutes=5 * step)
    ts = t.strftime("%Y-%m-%d %H:%M:%S")
    for i, host in enumerate(("alpha", "beta")):
        cpu = round(40 + 25 * math.sin(step / 7.0 + i * 1.6) + 5 * math.sin(step * 1.3), 2)
        req = int(300 + 120 * math.sin(step / 5.0 + i) + (step % 7) * 6)
        run(f"INSERT INTO Demo_Metrics VALUES ('{ts}','{host}',{cpu},{req})"); n += 1
print(f"seeded {n} rows")
PY
