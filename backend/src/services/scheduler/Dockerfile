FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY backend/pyproject.toml ./
COPY backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --system --compile-bytecode .

COPY backend/src ./src
ENV PYTHONPATH=/app/src


