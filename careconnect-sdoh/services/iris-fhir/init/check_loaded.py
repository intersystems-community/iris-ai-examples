import os
import sys
import httpx

FHIR_BASE = os.environ.get(
    "FHIR_BASE", "http://localhost:52773/csp/healthshare/demo/fhir/r4"
)


def already_loaded() -> bool:
    try:
        r = httpx.get(f"{FHIR_BASE}/Patient", params={"_count": 1}, timeout=10)
        bundle = r.json()
        total = bundle.get("total", 0)
        entries = len(bundle.get("entry", []))
        return total > 0 or entries > 0
    except Exception:
        return False


if __name__ == "__main__":
    if already_loaded():
        print("FHIR data already loaded — skipping (idempotent)")
        sys.exit(0)
    print("No patients found — proceeding with load")
    sys.exit(1)
