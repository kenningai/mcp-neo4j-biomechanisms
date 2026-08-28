FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN uv pip install --system mcp-neo4j-biomechanisms==0.3.0

EXPOSE 8000

CMD ["mcp-neo4j-biomechanisms"]