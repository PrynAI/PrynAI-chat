import asyncio
import chainlit as cl
import httpx
import os

GATEWAY_BASE = os.environ.get("GATEWAY_URL", "http://localhost:8080")

@cl.on_chat_start
async def start():
    await cl.Message(content="Hi! I’m ready.").send()

@cl.on_message
async def handle_message(message: cl.Message):
    endpoint = f"{GATEWAY_BASE}/api/chat/stream"
    data = {"message": message.content, "thread_id": None}
    msg = cl.Message(content="")
    await msg.send()
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream("POST", endpoint, json=data, headers={"accept": "text/event-stream"}) as r:
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data: "):
                        token = line.removeprefix("data: ")
                        await msg.stream_token(token)
                    elif line.startswith("event: done"):
                        break
        await msg.update()
    except Exception as e:
        await cl.Message(content=f"Error: {e}").send()
