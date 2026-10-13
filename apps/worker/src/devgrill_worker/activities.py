"""Activities: the only place workflows touch the outside world."""

from __future__ import annotations

from temporalio import activity


@activity.defn
async def pong(name: str) -> str:
    # `name` is a reserved LogRecord attribute, so log it under another key.
    activity.logger.info("pong", extra={"ping_name": name})
    return f"pong:{name}"
