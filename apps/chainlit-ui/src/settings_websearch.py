# apps/chainlit-ui/src/settings_websearch.py
import chainlit as cl
from chainlit.input_widget import Switch

WEB_SEARCH_KEY = "web_search"

async def inject_settings_ui() -> None:
    """Render the Chat Settings panel with a single 'Web search' switch."""
    await cl.ChatSettings([
        Switch(
            id=WEB_SEARCH_KEY,
            label="Web search (OpenAI)",
            initial=False,
            tooltip="Allow the model to use OpenAI's built-in Web Search tool."
        ),
    ]).send()
    # Seed a default so the first turn has a value
    cl.user_session.set("chat_settings", {WEB_SEARCH_KEY: False})

@cl.on_settings_update
async def _on_settings_update(settings: dict):
    # Persist user settings in the session (restored automatically on resume)
    cl.user_session.set("chat_settings", settings or {WEB_SEARCH_KEY: False})

def is_web_search_enabled() -> bool:
    settings = cl.user_session.get("chat_settings") or {}
    return bool(settings.get(WEB_SEARCH_KEY, False))
