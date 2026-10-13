"""Fail if any repo text file (except Windows scripts) contains CRLF line endings.

Containers fail on CRLF in shell scripts, Dockerfiles and YAML, so CI enforces LF everywhere.
`--fix` rewrites offending text files to LF (binary files are always skipped: known
extensions plus any file containing a NUL byte).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CRLF_ALLOWED = {".ps1", ".cmd", ".bat"}
BINARY_EXT = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2",
    ".ttf", ".otf", ".pdf", ".zip", ".gz",
}  # fmt: skip


def repo_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],  # noqa: S607
        capture_output=True,
        check=True,
    ).stdout
    return [Path(p) for p in out.decode("utf-8").split("\0") if p]


def main() -> int:
    offenders = []
    for path in repo_files():
        if path.suffix.lower() in CRLF_ALLOWED | BINARY_EXT or not path.is_file():
            continue
        if b"\r\n" in path.read_bytes():
            offenders.append(path.as_posix())
    if offenders:
        print("CRLF line endings found (run `just eol-fix`):")
        for name in offenders:
            print(f"  {name}")
        return 1
    print("eol: all text files use LF")
    return 0


if __name__ == "__main__":
    sys.exit(main())
