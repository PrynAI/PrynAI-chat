# apps/agent-langgraph/my_agent/graphs/chat.py
from typing import Dict, Any
from langgraph.graph import MessagesState, StateGraph, START
from langchain_core.messages import AnyMessage
# NEW: import the feature module
from my_agent.features.web_search import llm_for_config

class ChatState(MessagesState):
    # MessagesState already provides: messages: list[AnyMessage]
    pass

def chat_node(state: ChatState, config: Dict[str, Any] | None = None) -> dict:
    llm = llm_for_config(config)
    ai_msg = llm.invoke(state["messages"])
    return {"messages": [ai_msg]}

builder = StateGraph(ChatState)
builder.add_node("chat", chat_node)
builder.add_edge(START, "chat")
graph = builder.compile()