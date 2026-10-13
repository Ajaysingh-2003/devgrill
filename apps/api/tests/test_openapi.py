import json

from devgrill_api.openapi_export import build_spec


def test_spec_is_deterministic() -> None:
    first = json.dumps(build_spec(), sort_keys=True)
    second = json.dumps(build_spec(), sort_keys=True)
    assert first == second


def test_spec_lists_health_routes() -> None:
    paths = build_spec()["paths"]
    assert isinstance(paths, dict)
    assert {"/healthz", "/readyz"} <= set(paths)
