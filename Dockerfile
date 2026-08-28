FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN uv pip install --system kenning-soma==0.4.0

EXPOSE 8000

CMD ["kenning-soma"]