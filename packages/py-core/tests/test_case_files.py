"""Case files (ADR 018): the shape of the questions, deterministic scoring, and whether every
drill's case file is fair: its evidence shows its clues, and the answer doesn't stand out."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from devgrill.domain import casefile
from devgrill.domain.spec import CaseEvidence, CaseFileSpec
from devgrill.sandbox.content import load_bundle, load_case_spec, load_evidence
from devgrill.sandbox.verifier import check

CONTENT = Path(__file__).resolve().parents[3] / "content"
#: Longer than this, the longest option gives the answer away.
MAX_LENGTH_TELL = 12


def _question(answer: str = "a") -> dict[str, Any]:
    return {
        "options": [
            {"key": "a", "text": "The first explanation"},
            {"key": "b", "text": "The second explanation"},
            {"key": "c", "text": "The third explanation"},
        ],
        "answer": answer,
        "explanation": "Why that one is right, in enough words to be worth reading.",
    }


def _spec(**changes: Any) -> CaseFileSpec:
    return CaseFileSpec.model_validate(
        {
            "schema": "devgrill/case-file@1",
            "clues": [{"panel": "logs", "contains": "boom", "note": "The log says boom."}],
            "root_cause": _question("a"),
            "mitigation": _question("b"),
            "fix": _question("c"),
            **changes,
        }
    )


def _evidence(**changes: Any) -> CaseEvidence:
    return CaseEvidence.model_validate(
        {
            "schema": "devgrill/case-evidence@1",
            "source_hash": "abc",
            "recorded_at": 1000.0,
            "duration_s": 70.0,
            "breached_after_s": 5.0,
            "samples": [],
            "logs": [{"t": 1.0, "service": "api", "line": "all quiet"}],
            "status": [],
            "deploys": {},
            "changes": {},
            "files": {},
            **changes,
        }
    )


def test_the_answer_must_be_one_of_the_options() -> None:
    with pytest.raises(ValidationError, match="not one of the options"):
        _spec(fix=_question("d"))
    keys_out_of_order = _question()
    keys_out_of_order["options"][0]["key"] = "b"
    with pytest.raises(ValidationError, match="in order"):
        _spec(fix=keys_out_of_order)


def test_scoring_is_deterministic_and_weighs_the_cause_most() -> None:
    spec = _spec()
    right = {"root_cause": "a", "mitigation": "b", "fix": "c"}
    assert casefile.score(spec, right).score == 100
    assert casefile.score(spec, {**right, "root_cause": "b"}).score == 50
    assert casefile.score(spec, {**right, "mitigation": "a"}).score == 75
    assert casefile.score(spec, {"root_cause": "b", "mitigation": "a", "fix": "a"}).score == 0
    assert sum(casefile.WEIGHTS.values()) == 100
    wrong = casefile.score(spec, {**right, "fix": "a"}).answers[2]
    assert (wrong.correct, wrong.choice, wrong.answer) == (False, "a", "c")


def test_option_order_is_stable_but_not_the_authors() -> None:
    options = _spec().root_cause.options
    first = casefile.shuffled("one-drill", "root_cause", options)
    assert casefile.shuffled("one-drill", "root_cause", options) == first
    orders = {
        tuple(o.key for o in casefile.shuffled(f"drill-{i}", "root_cause", options))
        for i in range(30)
    }
    assert len(orders) > 1


def test_missing_clues_are_found() -> None:
    spec = _spec()
    assert [c.contains for c in casefile.missing_clues(spec, _evidence())] == ["boom"]
    shown = _evidence(logs=[{"t": 1.0, "service": "api", "line": "it went boom here"}])
    assert casefile.missing_clues(spec, shown) == []
    in_commands = _spec(
        clues=[{"panel": "commands", "contains": "boom", "note": "It said so right there."}]
    )
    # A clue only counts in the panel it names.
    assert casefile.missing_clues(in_commands, shown)


# ---------------------------------------------------------------------------- the content


def _scenarios() -> Iterator[Path]:
    return iter(sorted(p.parent for p in CONTENT.glob("scenarios/*/*/scenario.yaml")))


@pytest.mark.parametrize("folder", list(_scenarios()), ids=lambda p: p.name)
def test_every_drill_ships_a_fair_case_file(folder: Path) -> None:
    spec = load_case_spec(folder)
    evidence = load_evidence(folder)
    assert casefile.missing_clues(spec, evidence) == []
    assert evidence.breached_after_s <= evidence.duration_s
    assert evidence.samples and evidence.logs and evidence.deploys
    # The recording is the incident, not a fix: it ends with the page still firing.
    assert evidence.duration_s >= 60
    bundle = load_bundle(CONTENT, folder.name)
    assert bundle.scenario.slo is not None
    targets = bundle.scenario.slo.targets()
    last = evidence.samples[-3:]
    assert sum(bool(check(targets, s.values)) for s in last) * 2 > len(last), "it ended healthy"
    for key in casefile.QUESTION_KEYS:
        q = casefile.question(spec, key)
        answer = next(o.text for o in q.options if o.key == q.answer)
        longest = max(len(o.text) for o in q.options if o.key != q.answer)
        assert len(answer) - longest <= MAX_LENGTH_TELL, f"{key}: the answer stands out by length"


def test_a_recording_names_no_sandbox() -> None:
    for path in CONTENT.glob("scenarios/*/*/case-file/evidence.json"):
        text = path.read_text(encoding="utf-8")
        assert "dg-record" not in text, path
        assert "record-" not in text.replace("record-keeping", ""), path
