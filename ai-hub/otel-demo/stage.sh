#!/bin/sh
# Stage the AI Hub build and write .env for the demo stack.
#
#   AI_CORE_BUILD=<dir with irisllm.so and the iris_llm wheel> \
#   AI_CORE_CLS=<ai-core checkout>/iris-llm/cls \
#   OPENAI_API_KEY=... LANGFUSE_PUBLIC_URL=http://<host>:3300 \
#   ./stage.sh
#
# No route to OpenAI? Use the bundled Ollama instead of OPENAI_API_KEY:
#   LOCAL_LLM=qwen3.8:27b ... ./stage.sh
#
# Both artifacts must be built for the target's architecture (linux x86_64 or
# aarch64). .env is written once, mode 600, with random secrets; rerunning keeps
# it. Neither build/ nor .env is tracked.
set -eu
HERE=$(cd "$(dirname "$0")" && pwd)
cd "$HERE"

: "${AI_CORE_BUILD:?set AI_CORE_BUILD}"
: "${AI_CORE_CLS:?set AI_CORE_CLS}"

rm -rf build
mkdir -p build/wheels
cp "$AI_CORE_BUILD/irisllm.so" build/irisllm.so
cp "$AI_CORE_BUILD"/iris_llm-*.whl build/wheels/
cp -R "$AI_CORE_CLS" build/ai-cls
[ -f "$AI_CORE_BUILD/SOURCE_COMMIT" ] && cp "$AI_CORE_BUILD/SOURCE_COMMIT" build/
echo "staged: $(ls build build/wheels | tr '\n' ' ')"

if [ -f .env ]; then
  echo ".env exists; left as is"
  exit 0
fi

LOCAL_LLM=${LOCAL_LLM:-}
[ -n "$LOCAL_LLM" ] || : "${OPENAI_API_KEY:?set OPENAI_API_KEY, or LOCAL_LLM for the bundled Ollama}"
: "${LANGFUSE_PUBLIC_URL:?set LANGFUSE_PUBLIC_URL (the URL a browser uses to reach Langfuse)}"
rnd() { od -An -tx1 -N"$1" /dev/urandom | tr -d ' \n'; }
PK="pk-lf-$(rnd 12)"
SK="sk-lf-$(rnd 16)"
umask 077
cat > .env <<EOF
OPENAI_API_KEY=${OPENAI_API_KEY:-}
IRIS_IMAGE=${IRIS_IMAGE:-intersystems/irishealth:2026.3.0AI.154.0}
IRIS_KEY_FILE=${IRIS_KEY_FILE:-./iris.key}
LANGFUSE_PUBLIC_URL=$LANGFUSE_PUBLIC_URL
LANGFUSE_INIT_PROJECT_ID=otel-demo
LANGFUSE_INIT_PROJECT_PUBLIC_KEY=$PK
LANGFUSE_INIT_PROJECT_SECRET_KEY=$SK
LANGFUSE_OTLP_AUTH=$(printf '%s:%s' "$PK" "$SK" | base64 | tr -d '\n')
LANGFUSE_INIT_USER_EMAIL=${LANGFUSE_INIT_USER_EMAIL:-demo@example.com}
LANGFUSE_INIT_USER_PASSWORD=$(rnd 8)
LANGFUSE_SALT=$(rnd 16)
LANGFUSE_ENCRYPTION_KEY=$(rnd 32)
NEXTAUTH_SECRET=$(rnd 16)
POSTGRES_PASSWORD=$(rnd 12)
CLICKHOUSE_PASSWORD=$(rnd 12)
REDIS_AUTH=$(rnd 12)
MINIO_ROOT_PASSWORD=$(rnd 12)
EOF
if [ -n "$LOCAL_LLM" ]; then
  printf 'COMPOSE_PROFILES=local-llm\nDEMO_LLM_BASE_URL=http://ollama:11434/v1\nDEMO_MODEL=%s\n' "$LOCAL_LLM" >> .env
fi
chmod 600 .env
echo "wrote .env (Langfuse login: $(grep ^LANGFUSE_INIT_USER_EMAIL .env | cut -d= -f2), password in .env)"
