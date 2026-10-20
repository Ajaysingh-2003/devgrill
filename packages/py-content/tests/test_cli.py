import json
import shutil
from pathlib import Path

import pytest

from devgrill_content.cli import list_scenarios, main

CONTENT = Path(__file__).resolve().parents[3] / "content"


def test_list_finds_scenarios(tmp_path: Path) -> None:
    scenario = tmp_path / "scenarios" / "caching" / "big-sale-meltdown"
    scenario.mkdir(parents=True)
    (scenario / "scenario.yaml").write_text("slug: big-sale-meltdown\n", encoding="utf-8")
    assert list_scenarios(tmp_path) == [scenario]


def test_list_command_runs(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list"]) == 0
    assert capsys.readouterr().out


def test_validate_passes_on_the_repo_content(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--root", str(CONTENT), "validate"]) == 0
    assert "0 problems" in capsys.readouterr().out


def test_validate_catches_a_patch_that_no_longer_applies(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "content"
    shutil.copytree(CONTENT, root, ignore=shutil.ignore_patterns(".reports", ".schema"))
    cache = root / "base-apps" / "shopkart" / "api" / "app" / "cache.py"
    cache.write_text(cache.read_text(encoding="utf-8").replace("def key(", "def cache_key("), encoding="utf-8")
    assert main(["--root", str(root), "validate"]) == 1
    err = capsys.readouterr().err
    assert "cache/key-format-change" in err
    assert "does not apply" in err


def test_validate_unknown_scenario(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--root", str(CONTENT), "validate", "no-such-thing"]) == 1


def test_schema_export(tmp_path: Path) -> None:
    assert main(["schema", "--out", str(tmp_path)]) == 0
    scenario = json.loads((tmp_path / "scenario.schema.json").read_text(encoding="utf-8"))
    assert "schema" in scenario["properties"]  # aliases, as authors write them
    assert {p.name for p in tmp_path.iterdir()} >= {"fault.schema.json", "base-app.schema.json"}
