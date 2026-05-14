# Set IMAGE to the tag produced by `docker load` from the EAP portal download.
# See README.md for download instructions.
ARG IMAGE=irishealth-community:2026.2.0AI.162.0
FROM $IMAGE

USER root

COPY --chown=${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} docker/iris.script /home/irisowner/irisdev/iris.script
COPY --chown=${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} src/CareConnect /src/CareConnect

USER ${ISC_PACKAGE_MGRUSER}
WORKDIR /home/irisowner

RUN iris start IRIS quietly \
 && iris session IRIS < /home/irisowner/irisdev/iris.script \
 && iris stop IRIS quietly

EXPOSE 1972 52773
ENTRYPOINT ["/tini", "--", "/iris-main"]
