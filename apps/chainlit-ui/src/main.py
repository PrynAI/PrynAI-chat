# apps/chainlit-ui/src/main.py
import chainlit as cl
import httpx
import os

from settings_websearch import inject_settings_ui, is_web_search_enabled

GATEWAY_BASE = os.environ.get("GATEWAY_URL", "http://localhost:8080")

@cl.on_chat_start
async def start():
    await inject_settings_ui()
    if not cl.user_session.get("access_token"):
        await cl.Message(
            content="You're not signed in. [Click here to sign in](/auth) then return to chat."
        ).send()
    else:
        await cl.Message(content="Hi! I'm ready.").send()

@cl.on_message
async def handle_message(message: cl.Message):
    endpoint = f"{GATEWAY_BASE}/api/chat/stream"
    payload = {
        "message": message.content,
        "thread_id": None,  # will be set once threads UI is added
        "web_search": is_web_search_enabled(),
    }

    out = cl.Message(content="")
    await out.send()

    token = cl.user_session.get("access_token")
    headers = {
        "accept": "text/event-stream",
    }
    if token:
        headers["authorization"] = f"Bearer {token}"

    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", endpoint, json=payload, headers=headers) as resp:
                current_event = "message"
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
                            await out.stream_token(data)
        await out.update()
    except Exception as e:
        await cl.Message(content=f"**Error:** {e}").send()
