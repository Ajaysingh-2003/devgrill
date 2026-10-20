"""Pure rules behind the workspace: beats, signatures, repo paths."""

from __future__ import annotations

import pytest

from devgrill.domain.events import beats_for_trigger, timed_beats, visible
from devgrill.domain.spec import Beat
from devgrill.infra.signing import SignatureError, sign_request, verify_request
from devgrill.sandbox.compose import safe_repo_path

BEATS = [
    Beat(persona="priya", say="Sale is live", at="T+20s"),
    Beat(persona="arjun", say="Restart didn't hold", when="postgres-db.restarted"),
    Beat(persona="arjun", say="Holding", when="state:mitigated"),
    Beat(persona="priya", say="Still there?", at="T+3m"),
]


def test_triggered_beats_fire_once() -> None:
    assert [i for i, _ in beats_for_trigger(BEATS, "state:mitigated", [])] == [2]
    assert beats_for_trigger(BEATS, "state:mitigated", [2]) == []
    assert [i for i, _ in beats_for_trigger(BEATS, "postgres-db.restarted", [0])] == [1]
    assert beats_for_trigger(BEATS, "api.deployed", []) == []


def test_timed_beats_in_firing_order() -> None:
    assert [(at, i) for at, i, _ in timed_beats(BEATS)] == [(20, 0), (180, 3)]


def test_spoilers_are_hidden() -> None:
    assert not visible("fault")
    assert not visible("trail")
    assert visible("beat") and visible("deploy")


def test_signatures_cover_method_path_and_body() -> None:
    secret = "s" * 40
    signature = sign_request(secret, 1000, "GET", "/internal/attempts/a/status", b"")
    verify_request(secret, "1000", signature, "GET", "/internal/attempts/a/status", b"", now=1000)
    for method, target, body in [
        ("POST", "/internal/attempts/a/status", b""),
        ("GET", "/internal/attempts/a/files", b""),
        ("GET", "/internal/attempts/a/status", b"{}"),
    ]:
        with pytest.raises(SignatureError):
            verify_request(secret, "1000", signature, method, target, body, now=1000)
    with pytest.raises(SignatureError, match="stale"):
        verify_request(
            secret, "1000", signature, "GET", "/internal/attempts/a/status", b"", now=2000
        )
    with pytest.raises(SignatureError):
        verify_request("", "1000", signature, "GET", "/x", b"", now=1000)


@pytest.mark.parametrize(
    "path", ["app/main.py", "config/app.env", "CHANGELOG.md", "a/b-c_d.e/f.py"]
)
def test_repo_paths_inside(path: str) -> None:
    assert safe_repo_path(path) == path


@pytest.mark.parametrize(
    "path",
    [
        "",
        "/etc/passwd",
        "../x",
        "app/../../x",
        ".git/config",
        ".git",
        "app//main.py",
        "app/./main.py",
        "a b.py",
        "app/\x00.py",
        "x" * 301,
        ".hidden",
    ],
)
def test_repo_paths_outside_or_odd(path: str) -> None:
    with pytest.raises(ValueError):
        safe_repo_path(path)
