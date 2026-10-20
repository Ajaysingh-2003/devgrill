FROM python:3.14-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN pip install --quiet "psycopg[binary]==3.3.6" "redis==8.1.0" "prometheus-client==0.26.0"
WORKDIR /srv/worker
COPY worker.py ./
EXPOSE 9100
CMD ["python", "worker.py"]
