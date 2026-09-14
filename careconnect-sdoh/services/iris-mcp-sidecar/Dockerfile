# MCP sidecar ships as part of the IRIS AI EAP.
# EAP participants: set IRIS_IMAGE in .env to your registry path.
# EAP enrollment: https://www.intersystems.com/early-access
ARG IMAGE=intersystemsdc/irishealth-community:2026.2
FROM $IMAGE

EXPOSE 8888
ENTRYPOINT ["/usr/irissys/bin/iris-mcp-server"]
CMD ["run"]
