# Compiled graph(s)


from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END

class AgentState(TypedDict, total=False):
    input: str
    output: str

def echo_node(state: AgentState) -> AgentState:
    text = state.get("input", "")
    return {"output": f"setup ok: {text}"}

workflow = StateGraph(AgentState)
workflow.add_node("echo", echo_node)
workflow.add_edge(START, "echo")
workflow.add_edge("echo", END)
graph = workflow.compile()