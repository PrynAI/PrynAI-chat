# apps/agent-langgraph/my_agent/graphs/chat.py
from typing import Dict, Any
from langgraph.graph import MessagesState, StateGraph, START
from langchain_core.messages import AnyMessage
from my_agent.features.web_search import llm_and_messages_for_config  # feature module

class ChatState(MessagesState):
    # MessagesState already has: messages: list[AnyMessage]
    pass

def chat_node(state: ChatState, config: Dict[str, Any] | None = None) -> dict:
    # Decide LLM + (optionally) prepend the system tip when web_search is ON.
    llm, messages = llm_and_messages_for_config(config, state["messages"])
    ai_msg = llm.invoke(messages)
    return {"messages": [ai_msg]}

builder = StateGraph(ChatState)
builder.add_node("chat", chat_node)
builder.add_edge(START, "chat")
graph = builder.compile()
