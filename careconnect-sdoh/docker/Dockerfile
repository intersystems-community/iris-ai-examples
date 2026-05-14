ARG IMAGE=docker.iscinternal.com/docker-intersystems/intersystems/irishealth-community:2026.2.0AI.162.0
FROM $IMAGE

USER root

COPY --chown=${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} services/iris-ai-hub/iris.script /home/irisowner/irisdev/iris.script
COPY --chown=${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} services/iris-ai-hub/init/ /init/
COPY --chown=${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} src/CareConnect/MCP/ /src/CareConnect/MCP/
COPY --chown=${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} src/CareConnect/Tools/ /src/CareConnect/Tools/

RUN chmod +x /init/entrypoint.sh

USER ${ISC_PACKAGE_MGRUSER}
WORKDIR /home/irisowner

RUN iris start IRIS quietly \
 && iris session IRIS < /home/irisowner/irisdev/iris.script \
 && iris stop IRIS quietly

EXPOSE 1972 52773
CMD ["-a", "/init/entrypoint.sh"]
