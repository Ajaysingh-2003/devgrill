"""Configuration: connection strings from the environment, tunables from config/app.env.

config/app.env is part of the repo and ships with every deploy, so a config change is a
commit you can find in `git log`, revert, and redeploy. The environment wins over the file.
"""

from __future__ import annotations

import os
from pathlib import Path


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip())


_load_env_file(Path(__file__).resolve().parent.parent / "config" / "app.env")


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://shopkart:shopkart@postgres:5432/shopkart"
)
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")

#: Postgres connections per API process. Four processes share the database's 100 slots.
DB_POOL_MIN = _int("DB_POOL_MIN", 2)
DB_POOL_MAX = _int("DB_POOL_MAX", 10)
#: How long a request waits for a free connection before giving up (seconds).
DB_POOL_TIMEOUT_S = float(os.environ.get("DB_POOL_TIMEOUT_S", "5"))
#: How long a query waits for a row or table lock before failing (milliseconds; 0 = forever).
DB_LOCK_TIMEOUT_MS = _int("DB_LOCK_TIMEOUT_MS", 0)
#: How long one query may run before Postgres cancels it (milliseconds; 0 = no limit).
DB_STATEMENT_TIMEOUT_MS = _int("DB_STATEMENT_TIMEOUT_MS", 0)

#: Product cache lifetime. 0 disables caching (every read hits Postgres).
CACHE_TTL_SECONDS = _int("CACHE_TTL_SECONDS", 300)
#: Namespace prefix for cache keys, bumped when the cached shape changes.
CACHE_KEY_PREFIX = os.environ.get("CACHE_KEY_PREFIX", "")

SERVICE_NAME = os.environ.get("SERVICE_NAME", "product-api")
GIT_SHA = os.environ.get("GIT_SHA", "dev")
