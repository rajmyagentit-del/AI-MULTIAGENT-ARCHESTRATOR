"""
MCP client wrappers for our two already-deployed specialist servers:
  - ai-sql-agent-mcp   (Project 1) -- exposes `ask_database`
  - ai-document-mcp    (Project 2) -- exposes `search_documents`

Both are real, independently-deployed MCP servers on Render's free tier.
This module speaks the MCP protocol to them (initialize handshake, then
a tools/call) and returns plain text, so the LangGraph nodes that use
these functions don't need to know anything about MCP internals.

A fresh session is opened per call rather than held open persistently,
because Render's free tier spins services down when idle -- a
long-lived connection would silently break on the next cold start.
"""

import logging

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from orchestrator.config import settings

logger = logging.getLogger(__name__)

_MCP_CALL_TIMEOUT_SECONDS = 90


async def _call_mcp_tool(server_url: str, tool_name: str, arguments: dict) -> str:
    """
    Open a fresh MCP session against server_url, call tool_name with
    arguments, and return the result as plain text.
    """
    try:
        async with streamablehttp_client(server_url) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)

                if result.isError:
                    error_text = "".join(
                        block.text for block in result.content if hasattr(block, "text")
                    )
                    raise RuntimeError(f"{tool_name} returned an error: {error_text}")

                return "".join(
                    block.text for block in result.content if hasattr(block, "text")
                )
    except Exception as exc:
        logger.error("MCP call to %s (%s) failed: %s", server_url, tool_name, exc)
        raise RuntimeError(
            f"Could not reach specialist at {server_url} (tool={tool_name}): {exc}"
        ) from exc


async def call_sql_agent(query: str) -> str:
    """Ask the live ai-sql-agent-mcp server a natural-language database question."""
    return await _call_mcp_tool(
        settings.sql_agent_mcp_url,
        "ask_database",
        {"question": query},
    )


async def call_document_agent(query: str) -> str:
    """Ask the live ai-document-mcp server to search ingested documents."""
    return await _call_mcp_tool(
        settings.document_agent_mcp_url,
        "search_documents",
        {"query": query},
    )
