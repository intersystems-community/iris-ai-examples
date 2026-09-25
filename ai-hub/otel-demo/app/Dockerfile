FROM python:3.12-slim-bookworm

# iris_llm is built from ai-core; stage.sh drops the wheel into build/wheels.
COPY build/wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl \
      fastapi "uvicorn[standard]" python-multipart intersystems-irispython \
      opentelemetry-sdk opentelemetry-exporter-otlp-proto-http

COPY app/demo_app /app/demo_app
WORKDIR /app
CMD ["uvicorn", "demo_app.main:app", "--host", "0.0.0.0", "--port", "8000"]
