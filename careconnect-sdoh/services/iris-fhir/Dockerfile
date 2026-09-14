ARG IMAGE=intersystemsdc/irishealth-community:2026.2
FROM $IMAGE

USER root
WORKDIR /home/irisowner/irisdev

COPY --chown=${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} merge.cpf /home/irisowner/irisdev/merge.cpf
COPY --chown=${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} iris.script /home/irisowner/irisdev/iris.script
COPY --chown=${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} disable_password_expiry.script /home/irisowner/irisdev/disable_password_expiry.script
COPY --chown=${ISC_PACKAGE_MGRUSER}:${ISC_PACKAGE_IRISGROUP} init/ /init/

RUN chmod +x /init/entrypoint.sh 2>/dev/null || true

USER ${ISC_PACKAGE_MGRUSER}

# Build-time FHIR setup — no ZPM, no network required.
# Foundation.Install + InstallInstance use classes already in irishealth-community.
RUN iris start IRIS && \
    iris merge IRIS /home/irisowner/irisdev/merge.cpf && \
    iris session IRIS < /home/irisowner/irisdev/iris.script && \
    iris session IRIS < /home/irisowner/irisdev/disable_password_expiry.script && \
    iris stop IRIS quietly

EXPOSE 52773 1972

CMD ["-a", "/init/entrypoint.sh"]
