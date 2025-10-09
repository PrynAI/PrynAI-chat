# apps/agent-langgraph/my_agent/features/web_search.py
"""
OpenAI Web Search helpers.

Behavior:
- When the session flag `configurable.web_search` is False → plain model, no tools.
- When True → prepend a system tip AND bind the built-in `web_search` tool,
  forcing one call to that tool via tool_choice="web_search".

References:
- OpenAI Web Search tool (Responses API): https://platform.openai.com/docs/guides/tools-web-search
- LangChain tool forcing via `tool_choice`: see "How to force models to call a tool".
"""

from __future__ import annotations
from typing import Any, Dict, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, AnyMessage

WEB_SEARCH_FLAG_KEY = "web_search"
WEB_SEARCH_TOOL_NAME = "web_search"  # we name it explicitly so we can force it

# A single, crisp instruction to steer the model when search is enabled.
SYSTEM_TIP_WHEN_SEARCH_ON = (
    "You have access to the web_search tool. "
    "When the user requests current or time‑sensitive facts (e.g., 'today', 'now', 'current', "
    "'latest', 'weather', 'price', 'score', 'release'), call web_search to gather up‑to‑date "
    "information before answering. Include the source URLs you used."
)

def should_use_web_search(config: Dict[str, Any] | None) -> bool:
    """Read `configurable.web_search` off the LangGraph config."""
    if not config:
        return False
    cfg = config.get("configurable") or {}
    return bool(cfg.get(WEB_SEARCH_FLAG_KEY, False))

def prepend_search_system_tip(messages: List[AnyMessage]) -> List[AnyMessage]:
    """Prepend the search system instruction once per turn."""
    return [SystemMessage(content=SYSTEM_TIP_WHEN_SEARCH_ON)] + list(messages)

def make_base_llm() -> ChatOpenAI:
    """
    Build a stream-capable LLM using the Responses API so built-in tools are available.
    """
    return ChatOpenAI(
        model="gpt-5-mini",
        temperature=0.3,
        streaming=True,
        use_responses_api=True,
        output_version="responses/v1",
        reasoning={"effort": "medium"},
    )

def with_openai_web_search(llm: ChatOpenAI, *, force_specific_tool: bool) -> ChatOpenAI:
    """
    Bind the GA web search tool. We pass an explicit 'name' so we can force it by name.
    In LangChain, bind_tools(..., tool_choice="<tool_name>") forces the model to call that tool.
    """
    tools = [{
        "type": "web_search",
        "name": WEB_SEARCH_TOOL_NAME,
        "description": "Search the web for up-to-date information."
    }]
    if force_specific_tool:
        return llm.bind_tools(tools, tool_choice=WEB_SEARCH_TOOL_NAME)
    return llm.bind_tools(tools, tool_choice="Auto")

def llm_and_messages_for_config(
    config: Dict[str, Any] | None,
    messages: List[AnyMessage],
) -> tuple[ChatOpenAI, List[AnyMessage]]:
    """
    Returns (llm, messages) with optional system tip and tool binding.
    - OFF  → (base LLM, original messages)
    - ON   → (LLM with web_search bound & required, messages with system tip prepended)
    """
    llm = make_base_llm()
    if not should_use_web_search(config):
        return llm, messages

    # Prepend the system tip and force a call to the web_search tool on this turn.
    msgs = prepend_search_system_tip(messages)
    llm = with_openai_web_search(llm, force_specific_tool=True)
    return llm, msgs
