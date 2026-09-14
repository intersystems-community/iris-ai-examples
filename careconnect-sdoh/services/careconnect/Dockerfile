FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000 8501

# Streamlit UI — placeholder until app.py is added to this directory.
# The MCP tool endpoint (/mcp/careconnect) in iris-ai-hub is the primary interface.
CMD ["bash", "-c", "echo 'CareConnect placeholder — MCP endpoint at careconnect-iris-hub:8888'; sleep infinity"]
