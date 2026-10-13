"""Write the OpenAPI document deterministically for the TypeScript client generator."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from devgrill.config import Settings
from devgrill_api.main import create_app

DEFAULT_OUT = Path("packages/api-client/openapi.json")


def build_spec() -> dict[str, object]:
    # No lifespan runs here, so no database or network is touched.
    return create_app(Settings(log_format="json")).openapi()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    out: Path = args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(build_spec(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    out.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
