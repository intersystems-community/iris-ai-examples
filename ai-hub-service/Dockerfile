# AI Hub Service image. Build from the repository root, because the offline
# CareConnect mode imports the eval suite's tool port from careconnect-sdoh/:
#
#   docker build -f ai-hub-service/Dockerfile -t aihub-service:0.1.0 .
#
# The image carries the three CareConnect configs; AIHUB_CONFIG picks one. A
# customer deployment mounts its own service.yaml at /etc/aihub instead.
FROM python:3.11-slim

WORKDIR /app/ai-hub-service
COPY ai-hub-service/requirements.txt .
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu 'torch>=2.5,<3' \
 && grep -v -E '^(pytest|torch)' requirements.txt > /tmp/req.txt \
 && pip install --no-cache-dir -r /tmp/req.txt

COPY ai-hub-service/src ./src
COPY ai-hub-service/examples ./examples
# Offline mode's tools: the faithful Python port of SDoHToolSet. Kept at the
# same relative path so offline.yaml's python_path resolves unchanged.
COPY careconnect-sdoh/evals/careconnect_evals /app/careconnect-sdoh/evals/careconnect_evals

ENV PYTHONPATH=/app/ai-hub-service/src \
    AIHUB_CONFIG=/app/ai-hub-service/examples/careconnect/offline.yaml \
    AIHUB_PORT=8080

RUN useradd --uid 10001 --no-create-home aihub
USER 10001

EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/healthz')"
CMD ["python", "-m", "aihub_service"]
