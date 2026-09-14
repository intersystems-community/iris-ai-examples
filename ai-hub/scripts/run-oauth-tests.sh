#!/usr/bin/env bash
# Run Sample.AI.OAuth integration tests against a dedicated iris-devtester container.
#
# Usage:
#   bash scripts/run-oauth-tests.sh [--keep] [--no-reuse]
#
# Options:
#   --keep      Keep container running after tests (default: stop+remove)
#   --no-reuse  Force container restart even if already running
#
# The container (aihub-oauth-test) runs whatever image IRIS_IMAGE names; it must be an
# AI Hub build, since the policy hooks live in %AI.*. Verified on 2026.3.0AI builds 139 and 141.
# Tests run inside irispython embedded Python context — the only way to access $Roles.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONTAINER_NAME="aihub-oauth-test"
KEEP=false
NO_REUSE=""

for arg in "$@"; do
    case $arg in
        --keep)    KEEP=true ;;
        --no-reuse) NO_REUSE="--no-reuse" ;;
    esac
done

cleanup() {
    if [[ "$KEEP" == "false" ]]; then
        echo "--- Stopping $CONTAINER_NAME ---"
        python3 "$SCRIPT_DIR/setup_oauth_test_container.py" --stop 2>/dev/null || true
    else
        echo "--- Keeping $CONTAINER_NAME running (--keep) ---"
    fi
}
trap cleanup EXIT

# ── Step 1: Start container and compile classes ───────────────────────────────
echo "=== Setting up $CONTAINER_NAME ==="
python3 "$SCRIPT_DIR/setup_oauth_test_container.py" $NO_REUSE

# ── Step 2: Copy test files into container ────────────────────────────────────
echo "=== Copying test files ==="
docker cp "$REPO_ROOT/tests/integration/test_oauth_rbac.py" \
    "$CONTAINER_NAME:/tmp/test_oauth_rbac.py"
docker cp "$REPO_ROOT/tests/integration/MockRBACPolicy.cls" \
    "$CONTAINER_NAME:/tmp/MockRBACPolicy.cls"
docker cp "$REPO_ROOT/tests/integration/MockRoleDiscovery.cls" \
    "$CONTAINER_NAME:/tmp/MockRoleDiscovery.cls"
# Compile mock helper classes
docker exec -u irisowner "$CONTAINER_NAME" \
    /usr/irissys/bin/irispython -c \
    'import iris; [iris.cls("%SYSTEM.OBJ").Load(f"/tmp/{f}", "c") for f in ["MockRBACPolicy.cls","MockRoleDiscovery.cls"]]' \
    2>/dev/null || true

# ── Step 3: Install pytest inside container if needed ─────────────────────────
echo "=== Ensuring pytest available ==="
docker exec --user root "$CONTAINER_NAME" \
    pip install --quiet --break-system-packages pytest 2>/dev/null \
    || docker exec "$CONTAINER_NAME" \
    /usr/irissys/bin/irispython -m pip install --quiet pytest 2>/dev/null \
    || true

# ── Step 4: Run tests via irispython ──────────────────────────────────────────
echo ""
echo "=== Running Sample.AI.OAuth tests (irispython) ==="
docker exec -u irisowner "$CONTAINER_NAME" \
    /usr/irissys/bin/irispython -m pytest /tmp/test_oauth_rbac.py -v --tb=short

echo ""
echo "=== All tests passed ==="
