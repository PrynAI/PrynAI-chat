
from typing import TypedDict, List
from langgraph.graph import MessagesState, StateGraph, START
from langchain_openai import ChatOpenAI
from langchain_core.messages import AnyMessage

class ChatState(MessagesState):
    # MessagesState already provides: messages: List[AnyMessage]
    pass

# Stream-capable LLM (model of your choice)
llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.3,
    #model="gpt-5-mini",  # pick your tiered model
    # reasoning={"effort": "medium"},
    # model_kwargs={"text": {"verbosity": "high"}},
    streaming=True,       # critical for token streaming
)

def chat_node(state: ChatState) -> dict:
    # Invoke on the full message list and append assistant reply as a message
    ai_msg = llm.invoke(state["messages"])
    return {"messages": [ai_msg]}

builder = StateGraph(ChatState)
builder.add_node("chat", chat_node)
builder.add_edge(START, "chat")
graph = builder.compile()


# langgraph dev -c langgraph.json