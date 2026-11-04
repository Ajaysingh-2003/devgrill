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


DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://ledger:ledger@postgres-db:5432/ledger")
DB_POOL_MIN = _int("DB_POOL_MIN", 2)
DB_POOL_MAX = _int("DB_POOL_MAX", 10)
DB_POOL_TIMEOUT_S = float(os.environ.get("DB_POOL_TIMEOUT_S", "5"))

#: The house account: it funds opening balances and clears card payments until the
#: merchant is paid out. It is the only account allowed below zero.
HOUSE_ACCOUNT = 0

SERVICE_NAME = os.environ.get("SERVICE_NAME", "ledger-api")
GIT_SHA = os.environ.get("GIT_SHA", "dev")
