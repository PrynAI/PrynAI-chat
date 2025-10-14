# apps/chainlit-ui/src/sse_utils.py
from __future__ import annotations
from typing import AsyncGenerator, Tuple

async def iter_sse_events(resp) -> AsyncGenerator[Tuple[str, str], None]:
    """
    Parse a Server‑Sent Events (SSE) stream and yield (event, data) tuples.
    - Collects consecutive `data:` lines and flushes on a blank line.
    - Preserves newlines within event data, per SSE spec.
    - Defaults to event="message" if none was set.
    """
    event = "message"
    buf: list[str] = []

    async for raw in resp.aiter_lines():
        if raw is None:
            continue
        line = raw.rstrip("\r")
        if line == "":
            # End of event → flush buffer
            data = "\n".join(buf)
            yield event, data
            event, buf = "message", []
            continue

        if line.startswith("event:"):
            # Support "event: foo" and "event:foo"
            _, val = line.split("event:", 1)
            event = val.strip() or "message"
            continue

        if line.startswith("data:"):
            # Support "data: xyz" and "data:xyz"
            _, val = line.split("data:", 1)
            buf.append(val.lstrip())
            continue

    # Flush trailing lines if the stream ends abruptly
    if buf:
        yield event, "\n".join(buf)