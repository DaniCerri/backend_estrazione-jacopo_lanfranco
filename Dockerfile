FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app

RUN useradd --system --no-create-home app
USER app

ENV PATH="/app/.venv/bin:$PATH" \
    PORT=8000

EXPOSE 8000

# "::" ascolta IPv4 e IPv6: serve per la rete privata Railway (*.railway.internal)
CMD ["sh", "-c", "exec uvicorn app.main:app --host :: --port ${PORT}"]
