#!/usr/bin/env bash
# Fetch a client-credentials access token for one of the three demo tiers.
#
#   ./get-token.sh read      # scope mcp.read  -> IRIS role SampleReader
#   ./get-token.sh write     # scope mcp.write -> IRIS role SampleWriter
#   ./get-token.sh admin     # scope mcp.admin -> IRIS role SampleAdmin
#
# Prints the raw access token on stdout, so it composes:
#   TOKEN=$(./get-token.sh read)
set -euo pipefail

TIER="${1:-}"
case "$TIER" in
read | write | admin) ;;
*)
  echo "usage: $0 <read|write|admin>" >&2
  exit 2
  ;;
esac

KEYCLOAK_URL="${KEYCLOAK_URL:-http://localhost:${KEYCLOAK_PORT:-55880}}"
REALM="${KEYCLOAK_REALM:-aihub}"

RESPONSE=$(curl -sS -X POST \
  "${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect/token" \
  -d grant_type=client_credentials \
  -d "client_id=mcp-${TIER}" \
  -d "client_secret=${TIER}-secret")

TOKEN=$(printf '%s' "$RESPONSE" |
  python3 -c 'import sys,json; print(json.load(sys.stdin).get("access_token",""))')

if [ -z "$TOKEN" ]; then
  echo "no access_token in response: $RESPONSE" >&2
  exit 1
fi

printf '%s\n' "$TOKEN"
