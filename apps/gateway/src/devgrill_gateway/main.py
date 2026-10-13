"""Gateway skeleton. Phase 4 swaps the echo socket for ticket-authenticated PTY + telemetry."""

from __future__ import annotations

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from devgrill import __version__
from devgrill.config import Settings, get_settings
from devgrill.observability import configure_logging

MAX_FRAME_BYTES = 64 * 1024


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    app = FastAPI(title="DevGrill Gateway", version=__version__)

    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.websocket("/gw/v1/echo")
    async def echo(websocket: WebSocket) -> None:
        await websocket.accept()
        try:
            while True:
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break
                if (data := message.get("bytes")) is not None:
                    if len(data) > MAX_FRAME_BYTES:
                        await websocket.close(code=1009)
                        break
                    await websocket.send_bytes(data)
                elif (text := message.get("text")) is not None:
                    if len(text) > MAX_FRAME_BYTES:
                        await websocket.close(code=1009)
                        break
                    await websocket.send_text(text)
        except WebSocketDisconnect:
            pass

    return app
