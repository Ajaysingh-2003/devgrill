"""A pretend payment provider (think Stripe), as ShopKart sees it from the outside.

  POST /charges {"order_id", "amount_cents"}  -> 201 a new charge (and a receipt email)
      Idempotency-Key: <key>                  -> a repeat of a finished key returns the same
                                                 charge (200); one still running answers 409
  GET  /charges?order_id=<id>                 -> every charge made for that order
  GET  /healthz, /metrics

Rate limit: RATE_LIMIT_PER_S calls (default 200) in any one second, counting every call,
refused ones too (as many real providers do); over it, 429 with Retry-After: 1.

Port 8081 is the sandbox's control panel for faults and probes, not part of the provider:
  POST /_config {"latency_ms", "slow_share", "slow_ms", "drop_share", "rate_limit", "down_s"}
  (drop_share: the share of charges whose answer is lost on the way back: charged, but the
  caller only sees the connection close)
"""

from __future__ import annotations

import json
import os
import random
import secrets
import socket
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

config: dict[str, float] = {
    "latency_ms": float(os.environ.get("LATENCY_MS", "5")),
    "slow_share": float(os.environ.get("SLOW_SHARE", "0")),
    "slow_ms": float(os.environ.get("SLOW_MS", "1000")),
    "drop_share": 0.0,
    "rate_limit": float(os.environ.get("RATE_LIMIT_PER_S", "200")),
    "down_until": 0.0,
}

lock = threading.Lock()
calls: deque[float] = deque()
charges: dict[int, list[dict[str, Any]]] = {}
by_key: dict[str, dict[str, Any] | None] = {}  # None while the first request is running
counters: dict[str, int] = {}


def count(name: str) -> None:
    counters[name] = counters.get(name, 0) + 1


def limited() -> bool:
    """Every call counts against the last second's quota, refused ones too."""
    now = time.monotonic()
    with lock:
        calls.append(now)
        while calls and calls[0] < now - 1.0:
            calls.popleft()
        return len(calls) > config["rate_limit"]


class Gateway(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def setup(self) -> None:
        super().setup()
        # Headers and body go out as separate writes: without this, Nagle's algorithm and the
        # caller's delayed ACK add 40 ms to every answer on a kept-alive connection.
        self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def reply(self, status: int, body: Any, headers: dict[str, str] | None = None) -> None:
        data = (body if isinstance(body, str) else json.dumps(body)).encode()
        self.send_response(status)
        content_type = "text/plain; version=0.0.4" if isinstance(body, str) else "application/json"
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        url = urlparse(self.path)
        if url.path == "/healthz":
            self.reply(200, {"status": "ok"})
        elif url.path == "/metrics":
            self.reply(200, metrics())
        elif url.path == "/charges":
            order_id = int(parse_qs(url.query).get("order_id", ["0"])[0])
            with lock:
                self.reply(200, list(charges.get(order_id, [])))
        else:
            self.reply(404, {"error": "not found"})

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            body = None
        if self.server.server_address[1] == 8081:
            return self.control(body if isinstance(body, dict) else {})
        if urlparse(self.path).path != "/charges":
            return self.reply(404, {"error": "not found"})
        if limited():
            with lock:
                count('payments_requests_total{result="limited"}')
            return self.reply(429, {"error": "rate limited"}, {"Retry-After": "1"})
        if time.monotonic() < config["down_until"]:
            with lock:
                count('payments_requests_total{result="unavailable"}')
            return self.reply(503, {"error": "payments are temporarily unavailable"})
        if not isinstance(body, dict) or not isinstance(body.get("order_id"), int):
            with lock:
                count('payments_requests_total{result="declined"}')
            return self.reply(400, {"error": "order_id is required"})
        key = self.headers.get("Idempotency-Key")
        if key:
            with lock:
                if key in by_key:
                    done = by_key[key]
                    result = "replayed" if done else "in_progress"
                    count(f'payments_requests_total{{result="{result}"}}')
                    if done is None:
                        return self.reply(409, {"error": "a request with this key is in progress"})
                    return self.reply(200, {**done, "replayed": True})
                by_key[key] = None
        # The work: the card network takes a while, and the charge happens whether or not the
        # caller is still waiting for the answer.
        slow = random.random() < config["slow_share"]
        time.sleep((config["slow_ms"] if slow else config["latency_ms"]) / 1000)
        charge = {
            "id": f"ch_{secrets.token_hex(8)}",
            "order_id": body["order_id"],
            "amount_cents": int(body.get("amount_cents") or 0),
            "receipt": "sent",
        }
        with lock:
            repeat = bool(charges.get(body["order_id"]))
            charges.setdefault(body["order_id"], []).append(charge)
            if key:
                by_key[key] = charge
            count('payments_requests_total{result="charged"}')
            count(f'payments_charges_total{{repeat="{str(repeat).lower()}"}}')
            count("payments_receipts_total")
        if random.random() < config["drop_share"]:
            self.close_connection = True  # charged, but the answer never arrives
            return
        self.reply(201, charge)

    def control(self, body: dict[str, Any]) -> None:
        with lock:
            for name in ("latency_ms", "slow_share", "slow_ms", "drop_share", "rate_limit"):
                if name in body:
                    config[name] = float(body[name])
            if "down_s" in body:
                config["down_until"] = time.monotonic() + float(body["down_s"])
        self.reply(200, {k: v for k, v in config.items() if k != "down_until"})


def metrics() -> str:
    lines = [
        "# TYPE payments_requests_total counter",
        "# TYPE payments_charges_total counter",
        "# TYPE payments_receipts_total counter",
    ]
    with lock:
        # Every series exists from the start, so rates and ratios have a baseline.
        for result in ("charged", "replayed", "in_progress", "limited", "unavailable", "declined"):
            name = f'payments_requests_total{{result="{result}"}}'
            lines.append(f"{name} {counters.get(name, 0)}")
        for repeat in ("false", "true"):
            name = f'payments_charges_total{{repeat="{repeat}"}}'
            lines.append(f"{name} {counters.get(name, 0)}")
        lines.append(f"payments_receipts_total {counters.get('payments_receipts_total', 0)}")
    return "\n".join(lines) + "\n"


def serve(port: int) -> None:
    server = ThreadingHTTPServer(("0.0.0.0", port), Gateway)  # noqa: S104 (a container)
    server.daemon_threads = True
    server.serve_forever()


if __name__ == "__main__":
    threading.Thread(target=serve, args=(8081,), daemon=True).start()
    serve(8080)
