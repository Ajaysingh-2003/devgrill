# The on-call engineer's shell: psql, redis-cli, curl, git, tmux and the devgrill CLI.
# The API source is mounted at /workspace/api (a git repo); deploys rebuild from it.
FROM python:3.14-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 TERM=xterm-256color
RUN apt-get update && apt-get install -y --no-install-recommends \
        postgresql-client redis-tools curl git tmux jq less procps nano vim-tiny \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --quiet "httpx==0.28.1" "redis==8.1.0"
COPY devgrill /usr/local/bin/devgrill
RUN chmod +x /usr/local/bin/devgrill \
    && git config --system user.email "oncall@shopkart.test" && git config --system user.name "On-call" \
    && git config --system safe.directory '*' \
    && printf 'export PS1="\\[\\e[36m\\]oncall@shopkart\\[\\e[0m\\]:\\w\\$ "\ncd /workspace/api 2>/dev/null\n' > /etc/profile.d/shopkart.sh
WORKDIR /workspace
CMD ["sleep", "infinity"]
