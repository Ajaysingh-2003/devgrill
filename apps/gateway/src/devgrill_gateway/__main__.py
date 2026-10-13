"""`uv run devgrill-gateway` starts the gateway with auto-reload in dev."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    reload = os.environ.get("DEVGRILL_ENV", "dev") == "dev"
    uvicorn.run(
        "devgrill_gateway.main:create_app",
        factory=True,
        host=os.environ.get("GATEWAY_HOST", "127.0.0.1"),
        port=int(os.environ.get("GATEWAY_PORT", "8100")),
        reload=reload,
        reload_dirs=["apps/gateway/src", "packages/py-core/src"] if reload else None,
    )


if __name__ == "__main__":
    main()
