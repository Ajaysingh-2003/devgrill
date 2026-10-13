# 007. SandboxDriver abstraction

Date: 2026-10-13 · Status: accepted (implemented from phase 3)

## Context
Scenarios must run on Docker Compose locally now (owner decision: local only), and later on Sysbox or Firecracker or a hosted provider (Track H), without rewriting content.

## Decision
All sandbox operations go through a `SandboxDriver` protocol in `devgrill.infra`: create, wait_healthy, apply_fault, exec_pty, exec, read_file, write_file, deploy, logs, metrics, network_endpoint, snapshot, destroy. Scenarios never reference a runtime. Phase 3 implements `ComposeDriver` only. The verifier always runs **outside** the sandbox.

## Consequences
Driver contract tests become the acceptance suite for any future driver. On Windows, the ComposeDriver talks to Docker over the `npipe` named pipe via aiodocker, which must be covered by an integration test.

## Alternatives considered
Calling `docker compose` CLI directly from domain code: fastest to write, impossible to swap later.
