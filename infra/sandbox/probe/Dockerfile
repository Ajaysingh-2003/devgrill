# The platform's eyes and hands inside a sandbox (PLAN §12.3, ADR 012, ADR 014). It sits on
# the sandbox network next to the app, but the player never gets a shell in it: scrapes, the
# load generator, Toxiproxy admin calls, verifier checks, database and cache insights, and the
# `control:7000` relay for the in-sandbox CLI run here, out of reach of root in the player's
# shell. Built by `devgrill-content build` as devgrill/sandbox-probe:1.
FROM grafana/k6:2.3.0 AS k6

FROM python:3.14-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl postgresql-client redis-tools procps \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --quiet "psycopg[binary]==3.3.6" "redis==8.1.0" "httpx==0.28.1"
COPY --from=k6 /usr/bin/k6 /usr/local/bin/k6
COPY scrape.sh /usr/local/bin/dg-scrape
COPY dg-sql dg-cache dg-relay dg-recovery /usr/local/bin/
RUN chmod +x /usr/local/bin/dg-scrape /usr/local/bin/dg-sql /usr/local/bin/dg-cache /usr/local/bin/dg-relay \
        /usr/local/bin/dg-recovery \
    && mkdir -p /probe/load /probe/verify /probe/out
WORKDIR /probe
CMD ["sleep", "infinity"]
