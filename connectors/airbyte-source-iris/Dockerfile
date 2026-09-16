# Manual/local build only.
#
# Airbyte's current contribution convention does NOT require (or generally want) a
# connector-local Dockerfile: `metadata.yaml`'s `connectorBuildOptions.baseImage` names
# a base image, and Airbyte's `airbyte-ci` tooling builds the final image from that
# base plus this connector's `pyproject.toml`/source at PR/publish time. See
# PUBLISHING.md "Build convention" for what was actually confirmed about this (fetched
# several current airbytehq/airbyte connectors' directories; none of the Python-CDK
# ones — e.g. source-firebolt, source-google-sheets — have a Dockerfile at all) and
# what remains a documentation citation rather than a live airbyte-ci run.
#
# This Dockerfile exists so the connector can still be built and run manually with
# plain `docker build`/`docker run` outside airbyte-ci, matching the "Dockerfile"
# deliverable this task asked for. It has NOT been built or run — there is no Docker
# daemon in this environment (see STATUS.md).

FROM python:3.11-slim

WORKDIR /airbyte/integration_code

COPY pyproject.toml README.md ./
COPY source_iris ./source_iris

RUN pip install --no-cache-dir .

ENV AIRBYTE_ENTRYPOINT="python -m source_iris.run"
ENTRYPOINT ["python", "-m", "source_iris.run"]

LABEL io.airbyte.version=0.1.0
LABEL io.airbyte.name=airbyte/source-iris
