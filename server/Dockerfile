# syntax=docker/dockerfile:1
# Backend image: Python 3.12, dependencies locked by uv, runs as a non-root user.
# Build from the repository root:  docker build -t sprawdzam-backend server/
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY --from=ghcr.io/astral-sh/uv:0.8.9 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev

COPY app ./app

RUN useradd --create-home --uid 10001 sprawdzam \
    && mkdir -p /app/data \
    && chown sprawdzam:sprawdzam /app/data
USER sprawdzam

ENV PATH="/app/.venv/bin:${PATH}" \
    DATA_DIR=/app/data

EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/health', timeout=3)"]

# One worker: call admission, the app hub and the cost guard keep state per process.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8765", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
