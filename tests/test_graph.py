"""
Unit tests for orchestrator.graph.

route_after_supervisor is tested directly as a pure function -- it's
the actual routing decision (call tools vs. end) and deserves its own
explicit coverage regardless of what the LLM or tools do.

test_full_graph_routes_to_correct_specialist mocks _llm.ainvoke to
control exactly what "Claude" decides, and mocks the underlying
mcp_clients/web_agent functions so no real external calls happen --
this proves the supervisor<->tools loop wiring itself is correct
(the graph structure, not the LLM's judgment, which was already
proven via live manual testing).
"""

import pytest
from unittest.mock import AsyncMock, patch
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from orchestrator.graph import route_after_supervisor, orchestrator_graph


def test_route_after_supervisor_goes_to_tools_when_tool_calls_present():
    ai_message = AIMessage(
        content="",
        tool_calls=[{"name": "ask_database", "args": {"question": "hi"}, "id": "1"}],
    )
    state = {"messages": [HumanMessage(content="hi"), ai_message]}

    assert route_after_supervisor(state) == "tools"


def test_route_after_supervisor_ends_when_no_tool_calls():
    ai_message = AIMessage(content="Here's your answer.")
    state = {"messages": [HumanMessage(content="hi"), ai_message]}

    from langgraph.graph import END
    assert route_after_supervisor(state) == END


@pytest.mark.asyncio
async def test_full_graph_routes_to_sql_specialist():
    """Mocks the LLM to first request ask_database, then give a final
    answer -- proves the supervisor<->tools loop itself works, without
    depending on real Claude judgment or a live SQL server."""
    tool_call_response = AIMessage(
        content="",
        tool_calls=[
            {"name": "ask_database", "args": {"question": "How many customers?"}, "id": "call_1"}
        ],
    )
    final_response = AIMessage(content="You have 3 customers.")

    mock_llm = AsyncMock()
    mock_llm.ainvoke = AsyncMock(side_effect=[tool_call_response, final_response])

    with patch("orchestrator.graph._llm", mock_llm), \
         patch("orchestrator.graph.call_sql_agent", AsyncMock(return_value='{"rows": [{"count": 3}]}')):
        result = await orchestrator_graph.ainvoke(
            {"messages": [HumanMessage(content="How many customers?")]}
        )

    messages = result["messages"]
    assert any(isinstance(m, ToolMessage) for m in messages)
    assert messages[-1].content == "You have 3 customers."
    assert mock_llm.ainvoke.call_count == 2
