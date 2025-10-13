# apps/agent-langgraph/my_agent/graphs/chat.py
from typing import Optional
from langgraph.graph import MessagesState, StateGraph, START
from langchain_core.messages import AnyMessage
from langchain_core.runnables import RunnableConfig

from my_agent.features.web_search import llm_and_messages_for_config  # feature module
from my_agent.utils.checkpointer import make_checkpointer

class ChatState(MessagesState):
    # MessagesState already has: messages: list[AnyMessage]
    pass

def chat_node(state: ChatState, config: Optional[RunnableConfig] = None) -> dict:
    """
    Core chat node:
    - Decides which LLM to use (with or without web_search bound).
    - Optionally prepends a system tip when web_search is ON.
    - Invokes the LLM with the current messages and config.
    """
    llm, messages = llm_and_messages_for_config(config, state["messages"])
    ai_msg = llm.invoke(messages, config=config)  # forward config!
    return {"messages": [ai_msg]}

# --- Graph wiring ---
builder = StateGraph(ChatState)
builder.add_node("chat", chat_node)
builder.add_edge(START, "chat")

# Local dev can opt-in to MemorySaver; Cloud uses built-in Postgres checkpointer.
_cp = make_checkpointer()
graph = builder.compile(checkpointer=_cp) if _cp else builder.compile()