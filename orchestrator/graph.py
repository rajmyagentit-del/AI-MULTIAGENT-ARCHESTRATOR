"""
The orchestrator's core: a LangGraph supervisor that routes a user's
question to one or more of three specialists via native tool-calling.

  ask_database         -> SQL Agent (Project 1, live MCP server)
  search_documents      -> Document RAG Agent (Project 2, live MCP server)
  search_web            -> Web Research Agent (Tavily)

Shape: supervisor node (Claude, bound to all three tools) <-> tool node,
looping until the supervisor responds with no further tool calls, at
which point that response is the final answer.
"""

import logging

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import SystemMessage
from langchain_core.tools import tool
from langgraph.graph import StateGraph, MessagesState, END
from langgraph.prebuilt import ToolNode

from orchestrator.config import settings
from orchestrator.mcp_clients import call_sql_agent, call_document_agent
from orchestrator.web_agent import call_web_agent

logger = logging.getLogger(__name__)

SUPERVISOR_SYSTEM_PROMPT = """You are a multi-agent orchestrator with three specialist tools:

- ask_database: for questions about structured business data (customers,
  orders, sales figures, counts, aggregates) stored in a SQL database.
- search_documents: for questions about content inside ingested documents
  (reports, contracts, filings) -- anything requiring reading text that was
  uploaded, not a live database or the web.
- search_web: for questions needing current, external information not
  contained in the database or documents -- news, current events, anything
  time-sensitive or outside this organization's own data.

Call whichever tool(s) the question actually needs. A single question may
need more than one specialist (e.g. "what does our Q3 report say about
Vendor X, and what's the latest news on them?" needs both search_documents
and search_web). If a specialist's result is insufficient or errors, you
may try a different specialist or explain the limitation -- do not
fabricate an answer a specialist didn't actually provide.

Once you have enough information, synthesize a clear, direct answer citing
which specialist(s) it came from."""


@tool
async def ask_database(question: str) -> str:
    """Answer a question about structured business data (customers, orders,
    sales, counts) by querying the SQL database."""
    return await call_sql_agent(question)


@tool
async def search_documents(query: str) -> str:
    """Search ingested documents (reports, contracts, filings) for
    relevant passages."""
    return await call_document_agent(query)


@tool
async def search_web(query: str) -> str:
    """Search the live web for current, external information not
    contained in the database or documents."""
    return await call_web_agent(query)


_TOOLS = [ask_database, search_documents, search_web]

_llm = ChatAnthropic(
    model=settings.claude_model,
    api_key=settings.anthropic_api_key,
).bind_tools(_TOOLS)


async def supervisor_node(state: MessagesState) -> dict:
    """Calls Claude with the full message history plus the system prompt.
    Claude decides whether to call tool(s) or give a final answer."""
    messages = [SystemMessage(content=SUPERVISOR_SYSTEM_PROMPT)] + state["messages"]
    response = await _llm.ainvoke(messages)
    return {"messages": [response]}


def route_after_supervisor(state: MessagesState) -> str:
    """If the supervisor's last message requested tool calls, go run them;
    otherwise its response is the final answer, so end."""
    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return END


def build_graph():
    """Assembles and compiles the supervisor <-> tools graph."""
    graph = StateGraph(MessagesState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("tools", ToolNode(_TOOLS))

    graph.set_entry_point("supervisor")
    graph.add_conditional_edges(
        "supervisor",
        route_after_supervisor,
        {"tools": "tools", END: END},
    )
    # After tools run, always return to the supervisor to synthesize
    # or decide whether another specialist call is needed.
    graph.add_edge("tools", "supervisor")

    return graph.compile()


orchestrator_graph = build_graph()
