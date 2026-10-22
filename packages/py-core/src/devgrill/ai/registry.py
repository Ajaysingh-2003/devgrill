"""Versioned prompts (ADR 016): `prompts/<name>.md`, one file per prompt.

A prompt file has a small header and two sections:

    ---
    name: persona
    version: 3
    model: fast            # fast | judge (devgrill.config: llm_model_fast / llm_model_judge)
    reasoning: none        # optional: the model's reasoning effort
    max_output: 400        # optional: output token cap (reasoning included); default 1000
    ---
    # system
    ...instructions, with $placeholders...
    # user
    ...the request, with $placeholders...

Every LLM call records `name@version` (llm_calls.prompt_version, Langfuse), so a grade or a
reply can always be traced to the exact prompt that produced it. Bump `version` on any change;
the evals run on prompt changes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache
from importlib import resources
from string import Template
from typing import Literal

_HEADER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
_SECTION = re.compile(r"^# (system|user)\s*$", re.M)


class PromptError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Prompt:
    name: str
    version: int
    model: Literal["fast", "judge"]
    reasoning: str | None
    max_output: int
    system: str
    user: str

    @property
    def id(self) -> str:
        return f"{self.name}@{self.version}"

    def render(self, **values: str) -> tuple[str, str]:
        """(instructions, input) with every $placeholder filled; a missing one is an error."""
        try:
            return (
                Template(self.system).substitute(values),
                Template(self.user).substitute(values),
            )
        except KeyError as exc:
            raise PromptError(f"{self.id}: no value for ${exc.args[0]}") from exc


def parse_prompt(text: str) -> Prompt:
    match = _HEADER.match(text.replace("\r\n", "\n"))
    if not match:
        raise PromptError("a prompt starts with a --- header ---")
    header: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        header[key.strip()] = value.split("#", 1)[0].strip()
    body = text.replace("\r\n", "\n")[match.end() :]
    parts = _SECTION.split(body)
    sections = {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
    if set(sections) != {"system", "user"}:
        raise PromptError("a prompt has exactly a '# system' and a '# user' section")
    model = header.get("model", "fast")
    if model not in ("fast", "judge"):
        raise PromptError(f"model must be fast or judge, not {model!r}")
    return Prompt(
        name=header["name"],
        version=int(header["version"]),
        model=model,  # type: ignore[arg-type]
        reasoning=header.get("reasoning") or None,
        max_output=int(header.get("max_output") or 1000),
        system=sections["system"],
        user=sections["user"],
    )


@cache
def prompt(name: str) -> Prompt:
    """The packaged prompt `prompts/<name>.md`."""
    text = resources.files("devgrill.ai").joinpath("prompts", f"{name}.md").read_text("utf-8")
    loaded = parse_prompt(text)
    if loaded.name != name:
        raise PromptError(f"prompts/{name}.md declares name {loaded.name!r}")
    return loaded


def all_prompts() -> list[Prompt]:
    folder = resources.files("devgrill.ai").joinpath("prompts")
    return [
        prompt(entry.name.removesuffix(".md"))
        for entry in folder.iterdir()
        if entry.name.endswith(".md")
    ]
