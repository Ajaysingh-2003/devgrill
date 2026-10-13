# 009. Native-Windows development under corporate policy

Date: 2026-10-13 · Status: accepted

## Context
The owner develops on native Windows 11 (decision 2026-10-12) on a managed machine. Phase 0 found these constraints:
1. **`cmd.exe` is blocked by group policy** ("This program is blocked by group policy"). npm and pnpm run scripts and `.bin` shims through cmd by default, and so do `pnpm dlx`, `concurrently` and `npx`.
2. **A TLS-intercepting proxy** (Cisco Umbrella) breaks Node's bundled CA store (`UNABLE_TO_GET_ISSUER_CERT_LOCALLY`).
3. **`winget` cannot reach its sources.**
4. Some venv launcher executables (e.g. `pytest.exe`) are denied; `python -m <tool>` works.
5. `minio/minio` is no longer published on Docker Hub.
6. Some file-writing tools on this machine produce CRLF.

## Decision
- **Node:** `NODE_OPTIONS=--use-system-ca` (user env var) makes Node trust the Windows certificate store.
- **uv:** `UV_SYSTEM_CERTS=1` (in `.env`; `UV_NATIVE_TLS` is deprecated).
- **npm/pnpm `script-shell` = Git Bash** (`C:\Program Files\Git\bin\bash.exe`), set in the *user* config, not the repo, so Linux CI is unaffected.
- **Tools installed via PyPI and npm**: `uv` and `just` (the `rust-just` package) with `pip install --user`, `pnpm` with `npm i -g`. Python 3.14's user `Scripts` folder was added to the user PATH.
- **No shells in our own tooling**: `scripts/dev.py` spawns api, worker, gateway and `node …/next dev` directly; `just` uses PowerShell with one command per line (PowerShell 5.1 has no `&&`).
- Python tools run as `python -m <tool>` in recipes and CI.
- **Object storage: SeaweedFS** (`chrislusf/seaweedfs:4.48`, S3 API on :8333) instead of MinIO.
- **Line endings:** `.gitattributes` forces LF; `just eol-check` and CI fail on CRLF; `just eol-fix` repairs text files (binary-safe).

## Consequences
Everything in the repo works on Linux unchanged; the Windows-specific pieces are user-level config documented in the README. If policy changes, nothing in the repo needs to change.

## Alternatives considered
WSL2 development (the owner declined); asking IT for exceptions (still worth doing for cmd.exe).
