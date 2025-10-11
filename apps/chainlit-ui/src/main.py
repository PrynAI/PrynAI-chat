import os
import httpx
import chainlit as cl

from settings_websearch import inject_settings_ui, is_web_search_enabled

GATEWAY_BASE = os.environ.get("GATEWAY_URL", "http://localhost:8080")

@cl.on_chat_start
async def start():
    await inject_settings_ui()
    app_user = cl.user_session.get("user")  # set by Chainlit after auth succeeds
    if not app_user:
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
        "thread_id": None,  # hook threads later
        "web_search": is_web_search_enabled(),
    }

    # Pull the Entra access token from the authenticated user metadata.
    app_user = cl.user_session.get("user")
    token = None
    if app_user and getattr(app_user, "metadata", None):
        token = app_user.metadata.get("access_token")

    out = cl.Message(content="")
    await out.send()

    headers = {"accept": "text/event-stream"}
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
