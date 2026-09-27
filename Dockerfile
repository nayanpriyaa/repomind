# syntax=docker/dockerfile:1

FROM python:3.11-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv

ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt ./

RUN pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir --no-deps .


FROM python:3.11-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HF_HOME=/models \
    REPOSITORIES_ROOT=/repositories \
    DATABASE_PATH=/data/repomind.db

COPY --from=builder /opt/venv /opt/venv

RUN useradd \
      --create-home \
      --uid 10001 \
      repomind \
 && mkdir -p \
      /data \
      /repositories \
      /models \
 && chown -R \
      repomind:repomind \
      /data \
      /repositories \
      /models

WORKDIR /app

USER repomind

EXPOSE 8000

HEALTHCHECK \
    --interval=30s \
    --timeout=5s \
    --start-period=40s \
    --retries=3 \
    CMD python -c \
      "import urllib.request,sys; \
       sys.exit(0 if urllib.request.urlopen( \
       'http://127.0.0.1:8000/health', \
       timeout=4).status == 200 else 1)"

CMD ["uvicorn", "repomind.api.main:app", "--host", "0.0.0.0", "--port", "8000"]