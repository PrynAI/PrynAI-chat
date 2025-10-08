import chainlit as cl
import httpx
import os

# Gateway base URL is set via Container Apps env (or defaults for local dev)
GATEWAY_BASE = os.environ.get("GATEWAY_URL", "http://localhost:8080")

@cl.on_chat_start
async def start():
    # Simple welcome – unchanged from your current file
    await cl.Message(content="Hi! I'm ready.").send()

@cl.on_message
async def handle_message(message: cl.Message):
    """
    Sends the user message to the gateway's SSE endpoint and:
      - streams normal tokens into a single assistant bubble
      - shows a separate 'Safety notice' bubble when the gateway emits `event: policy`
      - stops on `event: done`
    """
    endpoint = f"{GATEWAY_BASE}/api/chat/stream"
    payload = {"message": message.content, "thread_id": None}

    # Create the assistant message we’ll progressively fill with tokens
    out_msg = cl.Message(content="")
    await out_msg.send()

    # Track current SSE event type per spec (default = standard message tokens)
    current_event = "message"

    try:
        async with httpx.AsyncClient(timeout=None) as client:
            # Use streaming and iterate *line by line* (SSE frames are line-based)
            # httpx docs: aiter_lines() streams decoded text lines.
            async with client.stream(
                "POST",
                endpoint,
                json=payload,
                headers={"accept": "text/event-stream"},
            ) as resp:

                async for raw_line in resp.aiter_lines():
                    if not raw_line:
                        continue

                    # Handle SSE event headers (e.g., "event: policy", "event: done")
                    if raw_line.startswith("event: "):
                        current_event = raw_line.split("event: ", 1)[1].strip()
                        # If the server signals done, we can finish early
                        if current_event == "done":
                            break
                        continue

                    # Handle SSE data frames ("data: <content>")
                    if raw_line.startswith("data: "):
                        data = raw_line[6:]  # strip "data: "

                        if current_event == "policy":
                            # Show a separate safety banner for clarity
                            await cl.Message(content=f"**Safety notice:** {data}").send()

                        elif current_event == "error":
                            # Surface gateway/server errors cleanly to the user
                            await cl.Message(content=f"**Error:** {data}").send()

                        else:
                            # Normal token chunk → stream into the main assistant message
                            await out_msg.stream_token(data)

                # Finalize the streaming message (renders the bubble)
        await out_msg.update()

    except Exception as e:
        # Fallback error bubble if the stream fails at client-side
        await cl.Message(content=f"**Error:** {e}").send()
