FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml .
COPY uv.lock .
COPY src/ ./src/

RUN uv sync --frozen --no-dev
RUN uv pip install --system streamlink

RUN mkdir -p /recordings

CMD ["uv", "run", "src/main.py"]
