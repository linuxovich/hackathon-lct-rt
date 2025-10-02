FROM ghcr.io/astral-sh/uv:alpine

RUN apk add --no-cache \
    gcc \
    musl-dev \
    python3-dev

WORKDIR /postprocessing

COPY . .
RUN uv sync --frozen

EXPOSE 8889
CMD ["uv", "run", "python", "main.py"]
