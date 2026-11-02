"""The provider's slow afternoon (fault data): one charge in ten takes a full second."""

import json
import urllib.request

req = urllib.request.Request(
    "http://127.0.0.1:8081/_config",
    data=json.dumps({"slow_share": 0.1, "slow_ms": 1000}).encode(),
    headers={"Content-Type": "application/json"},
)
print(urllib.request.urlopen(req, timeout=5).read().decode())  # noqa: S310 (fixed http URL)
