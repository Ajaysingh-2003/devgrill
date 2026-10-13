from pathlib import Path

import pytest

from devgrill_content.cli import list_scenarios, main


def test_list_finds_scenarios(tmp_path: Path) -> None:
    scenario = tmp_path / "scenarios" / "caching" / "big-sale-meltdown"
    scenario.mkdir(parents=True)
    (scenario / "scenario.yaml").write_text("slug: big-sale-meltdown\n", encoding="utf-8")
    assert list_scenarios(tmp_path) == [scenario]


def test_unimplemented_commands_exit_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["validate", "big-sale-meltdown"]) == 2
    assert "phase 3" in capsys.readouterr().err


def test_list_command_runs(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list"]) == 0
    assert capsys.readouterr().out
