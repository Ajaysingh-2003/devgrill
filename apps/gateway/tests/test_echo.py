import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from devgrill.config import Settings
from devgrill_gateway.main import MAX_FRAME_BYTES, create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, log_format="json")))  # type: ignore[call-arg]


def test_healthz(client: TestClient) -> None:
    assert client.get("/healthz").json()["status"] == "ok"


def test_echo_text_and_bytes(client: TestClient) -> None:
    with client.websocket_connect("/gw/v1/echo") as ws:
        ws.send_text("ls -la")
        assert ws.receive_text() == "ls -la"
        ws.send_bytes(b"\x1b[A")
        assert ws.receive_bytes() == b"\x1b[A"


def test_oversized_frame_is_rejected(client: TestClient) -> None:
    with client.websocket_connect("/gw/v1/echo") as ws:
        ws.send_bytes(b"x" * (MAX_FRAME_BYTES + 1))
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_bytes()
    assert exc.value.code == 1009
