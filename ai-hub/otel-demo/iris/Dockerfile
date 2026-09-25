# IRIS with a locally built AI Hub layer: irisllm.so and the %AI classes from an
# ai-core checkout (staged into build/ by stage.sh), plus the demo production.
# Build context is ai-hub/, so Sample.Interop comes from this repo.
ARG IRIS_IMAGE=intersystems/irishealth:2026.3.0AI.154.0
FROM $IRIS_IMAGE

COPY --chown=irisowner:irisowner otel-demo/build/irisllm.so /usr/irissys/bin/irisllm.so
COPY --chown=irisowner:irisowner otel-demo/build/ai-cls /opt/demo/ai-cls
COPY --chown=irisowner:irisowner objectscript/cls/Sample/Interop /opt/demo/interop
COPY --chown=irisowner:irisowner objectscript/cls/Sample/AI/Policies/OTelAuditPolicy.cls /opt/demo/interop/
COPY --chown=irisowner:irisowner otel-demo/iris/cls /opt/demo/cls
COPY --chown=irisowner:irisowner otel-demo/iris/install.script /opt/demo/install.script

RUN iris start IRIS \
 && iris session IRIS < /opt/demo/install.script | tee /tmp/install.log \
 && iris stop IRIS quietly \
 && grep -q "install errors=0" /tmp/install.log
