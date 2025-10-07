import chainlit as cl
from chainlit.input_widget import Switch
from typing import Dict

@cl.on_chat_start  
async def start():
    # Show a simple settings panel; you'll wire it to tools later
    settings = await cl.ChatSettings(
        [Switch(id="web_search", label="Web search", initial=False)]
    ).send()
    await cl.Message(content="PrynAI is alive. Upload files or say hi.").send()

@cl.on_settings_update
async def on_settings_update(settings: Dict):
    # Persist the toggle for routing to the gateway → LangGraph tools
    cl.user_session.set("web_search", bool(settings.get("web_search", False)))

@cl.on_message
async def handle_message(message: cl.Message):
    # Quick streaming echo to verify UI plumbing
    tokens = message.content.split()
    msg = await cl.Message(content="").send()
    for t in tokens:
        await msg.stream_token(t + " ")
    await msg.update()
