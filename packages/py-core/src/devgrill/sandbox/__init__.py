"""Sandboxes: isolated, resource-limited copies of a base app that scenarios break.

- `driver`: the SandboxDriver protocol (ADR 007) and the data it exchanges
- `baseapp`: the `base-app.yaml` spec
- `compose`: the Docker Engine implementation (local dev)
- `content`: loading scenarios and faults from the content folder for the driver
"""
