"""`uv run devgrill-api` starts the API with auto-reload in dev."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    reload = os.environ.get("DEVGRILL_ENV", "dev") == "dev"
    uvicorn.run(
        "devgrill_api.main:create_app",
        factory=True,
        host=os.environ.get("API_HOST", "127.0.0.1"),
        port=int(os.environ.get("API_PORT", "8000")),
        reload=reload,
        reload_dirs=["apps/api/src", "packages/py-core/src"] if reload else None,
    )


if __name__ == "__main__":
    main()
