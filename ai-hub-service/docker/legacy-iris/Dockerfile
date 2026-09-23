# The "legacy" IRIS for the sidecar demo: an IRIS release that predates AI Hub,
# running CareConnect's data and production with no %AI anywhere.
#
# Build from the repository root:
#   docker build -f ai-hub-service/docker/legacy-iris/Dockerfile .
#
# It loads only the CareConnect classes that need no AI Hub (the patient table,
# its seed, the production and its BS/BP/BO/messages) plus the version-neutral
# AIHub.* wrappers. tests/test_objectscript.py holds both lists to that.
ARG LEGACY_IRIS_VERSION=2025.3
FROM intersystemsdc/irishealth-community:${LEGACY_IRIS_VERSION}

USER root
COPY --chown=${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} careconnect-sdoh/src/CareConnect/Patient.cls /src/CareConnect/Patient.cls
COPY --chown=${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} careconnect-sdoh/src/CareConnect/Production.cls /src/CareConnect/Production.cls
COPY --chown=${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} careconnect-sdoh/src/CareConnect/Setup/DemoData.cls /src/CareConnect/Setup/DemoData.cls
COPY --chown=${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} careconnect-sdoh/src/CareConnect/Message/ /src/CareConnect/Message/
COPY --chown=${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} careconnect-sdoh/src/CareConnect/Service/ /src/CareConnect/Service/
COPY --chown=${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} careconnect-sdoh/src/CareConnect/Process/ /src/CareConnect/Process/
COPY --chown=${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} careconnect-sdoh/src/CareConnect/Operation/ /src/CareConnect/Operation/
COPY --chown=${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} ai-hub-service/objectscript/AIHub/ /src/AIHub/
COPY --chown=${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} ai-hub-service/docker/legacy-iris/iris.script /tmp/iris.script

USER ${ISC_PACKAGE_MGRUSER}
RUN iris start IRIS quietly \
 && iris session IRIS < /tmp/iris.script \
 && iris stop IRIS quietly

EXPOSE 1972 52773
