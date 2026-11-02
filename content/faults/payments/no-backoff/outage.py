"""The provider's blip (fault data): its charges answer 503 for 30 seconds, then it is fine.
Its rate limit is 60 calls a second, as on ShopKart's contract."""

import json
import urllib.request

req = urllib.request.Request(
    "http://127.0.0.1:8081/_config",
    data=json.dumps({"rate_limit": 60, "down_s": 30}).encode(),
    headers={"Content-Type": "application/json"},
)
print(urllib.request.urlopen(req, timeout=5).read().decode())  # noqa: S310 (fixed http URL)
