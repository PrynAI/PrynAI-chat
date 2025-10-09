# apps/chainlit-ui/src/main.py
import chainlit as cl
import httpx
import os

from .settings_websearch import inject_settings_ui, is_web_search_enabled  

GATEWAY_BASE = os.environ.get("GATEWAY_URL", "http://localhost:8080")

@cl.on_chat_start
async def start():
    await inject_settings_ui()  # NEW: shows the gear icon & toggle
    await cl.Message(content="Hi! I'm ready.").send()

@cl.on_message
async def handle_message(message: cl.Message):
    endpoint = f"{GATEWAY_BASE}/api/chat/stream"
    payload = {
        "message": message.content,
        "thread_id": None,
        "web_search": is_web_search_enabled(),  # include the web_search setting
    }

    out_msg = cl.Message(content="")
    await out_msg.send()

    current_event = "message"
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                endpoint,
                json=payload,
                headers={"accept": "text/event-stream"},
            ) as resp:

                async for raw_line in resp.aiter_lines():
                    if not raw_line:
                        continue
                    if raw_line.startswith("event: "):
                        current_event = raw_line.split("event: ", 1)[1].strip()
                        if current_event == "done":
                            break
                        continue
                    if raw_line.startswith("data: "):
                        data = raw_line[6:]
                        if current_event == "policy":
                            await cl.Message(content=f"**Safety notice:** {data}").send()
                        elif current_event == "error":
                            await cl.Message(content=f"**Error:** {data}").send()
                        else:
                            await out_msg.stream_token(data)
        await out_msg.update()
    except Exception as e:
        await cl.Message(content=f"**Error:** {e}").send()
