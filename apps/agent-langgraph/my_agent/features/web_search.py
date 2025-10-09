# apps/agent-langgraph/my_agent/features/web_search.py
"""
OpenAI Web Search feature helpers for the LangGraph agent.

- Always uses the Responses API so the model *can* call tools.
- Only binds the built-in `web_search` tool when the session flag is ON.
"""

from __future__ import annotations
from typing import Any, Dict
import os
from langchain_openai import ChatOpenAI


WEB_SEARCH_FLAG_KEY = "web_search"


def should_use_web_search(config: Dict[str, Any] | None) -> bool:
    """Read `configurable.web_search` off the LangGraph config."""
    if not config:
        return False
    cfg = config.get("configurable") or {}
    return bool(cfg.get(WEB_SEARCH_FLAG_KEY, False))


def make_base_llm() -> ChatOpenAI:
    """
    Build a stream-capable LLM in Responses mode.
    """
    
    return ChatOpenAI(
        model="gpt-5-mini",
        temperature=0.3,
        streaming=True,
        use_responses_api=True,     # enables built-in tools + annotations
        output_version="responses/v1",
        reasoning={"effort": "medium"},
    )


def with_openai_web_search(llm: ChatOpenAI) -> ChatOpenAI:
    """
    Bind the GA web search tool. (Older previews used 'web_search_preview'.)
    See: https://platform.openai.com/docs/guides/tools-web-search
    """
    return llm.bind_tools([{"type": "web_search", "name": "web_search", "description": "Search the web for up-to-date information"}])


def llm_for_config(config: Dict[str, Any] | None) -> ChatOpenAI:
    """
    Return an LLM that is optionally bound with web search based on config.
    """
    llm = make_base_llm()
    if should_use_web_search(config):
        llm = with_openai_web_search(llm)
    return llm
