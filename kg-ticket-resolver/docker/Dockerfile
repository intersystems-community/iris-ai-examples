ARG IMAGE=irishealth-community:2026.2.0AI.162.0
FROM $IMAGE

USER root

COPY --chown=${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} docker/iris.script /home/irisowner/irisdev/iris.script
COPY --chown=${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} docker/entrypoint.sh /entrypoint.sh
COPY --chown=${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} src/KGTicketResolver /src/KGTicketResolver
COPY --chown=${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} data/planetcare_demo_tickets.json /app/data/planetcare_demo_tickets.json
COPY --chown=${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} data/planetcare_wiki /app/wiki/

RUN chmod +x /entrypoint.sh

USER ${ISC_PACKAGE_MGRUSER}
WORKDIR /home/irisowner

RUN iris start IRIS quietly \
 && iris session IRIS < /home/irisowner/irisdev/iris.script \
 && iris stop IRIS quietly

EXPOSE 1972 52773
ENTRYPOINT ["/tini", "--", "/entrypoint.sh"]
