#!/usr/bin/env bash
# Builds the plugin and packs it the way the Grafana catalog expects:
#   scripts/package.sh            -> dist-zip/intersystems-iris-datasource-<version>.zip
# Order matters: the frontend, then every backend binary, then the source manifest (the validator's go-manifest
# check hashes the source files, so any edit after this step makes it fail), then the zip with a top-level
# folder named after the plugin id and executable binaries.
set -euo pipefail
cd "$(dirname "$0")/.."

ID="$(python3 -c 'import json;print(json.load(open("src/plugin.json"))["id"])')"
VERSION="$(python3 -c 'import json;print(json.load(open("package.json"))["version"])')"

npm ci --no-audit --no-fund
npm run build
go run github.com/magefile/mage -v buildAll
go run github.com/magefile/mage -v build:generateManifestFile

OUT="dist-zip"
rm -f "$OUT/$ID-$VERSION.zip"
mkdir -p "$OUT"
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
mkdir -p "$STAGE/$ID"
cp -R dist/. "$STAGE/$ID/"
chmod +x "$STAGE/$ID"/gpx_* 2>/dev/null || true
(cd "$STAGE" && zip -qr -X "$OLDPWD/$OUT/$ID-$VERSION.zip" "$ID")
shasum -a 1 "$OUT/$ID-$VERSION.zip"
