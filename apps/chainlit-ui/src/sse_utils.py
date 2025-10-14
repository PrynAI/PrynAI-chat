# apps/chainlit-ui/src/sse_utils.py
from __future__ import annotations
from typing import AsyncGenerator, Tuple

async def iter_sse_events(resp) -> AsyncGenerator[Tuple[str, str], None]:
    """
    Parse a Server-Sent Events (SSE) stream and yield (event, data) tuples.

    Behavior:
    - Collects consecutive 'data:' lines and flushes on a blank line.
    - Preserves all original newlines and spaces inside the event data.
    - Trims at most a single space after 'data:' per SSE spec.
    - Defaults to event='message' if none is set.
    """
    event = "message"
    buf: list[str] = []

    async for raw in resp.aiter_lines():
        if raw is None:
            continue
        line = raw.rstrip("\r")

        if line == "":
            # Blank line: end of the current event
            data = "\n".join(buf)
            yield event, data
            event, buf = "message", []
            continue

        if line.startswith("event:"):
            _, val = line.split("event:", 1)
            event = val.strip() or "message"
            continue

        if line.startswith("data:"):
            _, val = line.split("data:", 1)
            # Per SSE spec, remove one optional leading space after "data:"
            if val.startswith(" "):
                val = val[1:]
            buf.append(val)
            continue

    # Flush any trailing buffered data if stream ends without a blank line
    if buf:
        yield event, "\n".join(buf)