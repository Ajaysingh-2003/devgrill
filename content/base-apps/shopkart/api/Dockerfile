# ShopKart API image. The same source is a git repo in the tools container (/workspace/api);
# `devgrill deploy` copies app/ and config/ from there into /srv/app and restarts this service.
FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /srv/app
COPY pyproject.toml ./
RUN pip install --quiet \
    "fastapi==0.143.3" "uvicorn==0.54.0" "psycopg[binary,pool]==3.3.6" "redis==8.1.0" \
    "prometheus-client==0.26.0"
COPY app ./app
COPY config ./config

EXPOSE 8000
# Metric files from a previous run would double-count after a restart: start clean.
CMD ["sh", "-c", "rm -rf \"$PROMETHEUS_MULTIPROC_DIR\" && mkdir -p \"$PROMETHEUS_MULTIPROC_DIR\" && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4 --no-access-log"]
