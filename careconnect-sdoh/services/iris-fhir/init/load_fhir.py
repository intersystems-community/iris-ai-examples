import json
import os
import pathlib
import sys
import time

import httpx

FHIR_BASE = os.environ.get(
    "FHIR_BASE", "http://localhost:52773/csp/healthshare/demo/fhir/r4"
)
DATA_DIR = os.environ.get("SYNTHEA_DIR", "/synthea-data/fhir")
BATCH_SIZE = int(os.environ.get("LOAD_BATCH", "10"))


def wait_for_fhir(timeout: int = 120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"{FHIR_BASE}/metadata", timeout=5)
            if r.status_code == 200:
                print("FHIR server ready")
                return
        except Exception:
            pass
        time.sleep(5)
    print("ERROR: FHIR server not ready after timeout", file=sys.stderr)
    sys.exit(1)


def load_bundle(client: httpx.Client, path: str) -> bool:
    with open(path) as f:
        bundle = json.load(f)
    bundle["type"] = "transaction"
    for entry in bundle.get("entry", []):
        if "request" not in entry:
            resource = entry.get("resource", {})
            rtype = resource.get("resourceType", "Resource")
            rid = resource.get("id", "")
            entry["request"] = {
                "method": "PUT" if rid else "POST",
                "url": f"{rtype}/{rid}" if rid else rtype,
            }
    try:
        r = client.post(f"{FHIR_BASE}/", json=bundle, timeout=30)
        r.raise_for_status()
        return True
    except Exception as e:
        print(f"  WARN: failed to load {path}: {e}", file=sys.stderr)
        return False


def main():
    wait_for_fhir()

    data_path = pathlib.Path(DATA_DIR)
    if not data_path.exists():
        print(f"No data dir at {DATA_DIR} — checking fallback")
        fallback = pathlib.Path("/fallback-data")
        if fallback.exists():
            data_path = fallback
        else:
            print("No Synthea data found — skipping FHIR load", file=sys.stderr)
            return

    files = sorted(data_path.glob("*.json"))
    print(f"Loading {len(files)} FHIR bundles from {data_path}")

    with httpx.Client(timeout=30) as client:
        ok, fail = 0, 0
        for i, f in enumerate(files):
            if load_bundle(client, str(f)):
                ok += 1
            else:
                fail += 1
            if (i + 1) % BATCH_SIZE == 0:
                print(f"  Progress: {i + 1}/{len(files)} ({ok} ok, {fail} failed)")

    print(f"FHIR load complete: {ok} ok, {fail} failed")


if __name__ == "__main__":
    main()
