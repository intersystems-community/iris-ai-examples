#!/bin/bash
set -e

for i in $(seq 1 20); do
    iris session IRIS -U USER "write 1,! halt" >/dev/null 2>&1 && break
    sleep 3
done

echo "iris-fhir ready"
tail -f /dev/null
