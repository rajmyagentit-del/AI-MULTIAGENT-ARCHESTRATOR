"""
Unit tests for orchestrator.mcp_clients.

These mock the MCP session/transport layer rather than hitting the live
ai-sql-agent-mcp / ai-document-mcp servers. Live integration was already
verified manually (see commit history) -- these tests exist to catch
regressions in our own call_sql_agent / call_document_agent logic
(argument names, error handling, response unwrapping) without depending
on external services being reachable during CI.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from orchestrator.mcp_clients import call_sql_agent, call_document_agent


def _make_mock_result(text: str, is_error: bool = False):
    """Builds a fake MCP tool-call result matching the shape our code
    unwraps: result.isError and result.content[i].text"""
    block = MagicMock()
    block.text = text
    result = MagicMock()
    result.isError = is_error
    result.content = [block]
    return result


@pytest.mark.asyncio
async def test_call_sql_agent_sends_question_param():
    """Regression test for the real bug we hit: ask_database's parameter
    is 'question', not 'query'. This locks that in."""
    mock_session = AsyncMock()
    mock_session.call_tool.return_value = _make_mock_result('{"rows": []}')
    mock_session.initialize = AsyncMock()

    with patch("orchestrator.mcp_clients.streamablehttp_client") as mock_transport, \
         patch("orchestrator.mcp_clients.ClientSession") as mock_session_cls:
        mock_transport.return_value.__aenter__.return_value = (None, None, None)
        mock_session_cls.return_value.__aenter__.return_value = mock_session

        await call_sql_agent("How many customers?")

        mock_session.call_tool.assert_called_once_with(
            "ask_database", {"question": "How many customers?"}
        )


@pytest.mark.asyncio
async def test_call_document_agent_sends_query_param():
    """Regression test: search_documents' parameter is 'query'."""
    mock_session = AsyncMock()
    mock_session.call_tool.return_value = _make_mock_result('{"results": []}')
    mock_session.initialize = AsyncMock()

    with patch("orchestrator.mcp_clients.streamablehttp_client") as mock_transport, \
         patch("orchestrator.mcp_clients.ClientSession") as mock_session_cls:
        mock_transport.return_value.__aenter__.return_value = (None, None, None)
        mock_session_cls.return_value.__aenter__.return_value = mock_session

        await call_document_agent("management fees")

        mock_session.call_tool.assert_called_once_with(
            "search_documents", {"query": "management fees"}
        )


@pytest.mark.asyncio
async def test_call_sql_agent_raises_on_tool_error():
    """If the remote tool reports isError=True, we should surface a clear
    RuntimeError rather than silently returning the error text as if it
    were a valid answer."""
    mock_session = AsyncMock()
    mock_session.call_tool.return_value = _make_mock_result(
        "validation error", is_error=True
    )
    mock_session.initialize = AsyncMock()

    with patch("orchestrator.mcp_clients.streamablehttp_client") as mock_transport, \
         patch("orchestrator.mcp_clients.ClientSession") as mock_session_cls:
        mock_transport.return_value.__aenter__.return_value = (None, None, None)
        mock_session_cls.return_value.__aenter__.return_value = mock_session

        with pytest.raises(RuntimeError, match="ask_database returned an error"):
            await call_sql_agent("bad question")


@pytest.mark.asyncio
async def test_call_sql_agent_wraps_connection_failure():
    """If the transport itself fails (e.g. server unreachable), we should
    get a clear RuntimeError naming the server and tool, not a raw/opaque
    exception from deep inside the MCP library."""
    with patch(
        "orchestrator.mcp_clients.streamablehttp_client",
        side_effect=ConnectionError("connection refused"),
    ):
        with pytest.raises(RuntimeError, match="Could not reach specialist"):
            await call_sql_agent("How many customers?")
