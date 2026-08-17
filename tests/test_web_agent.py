"""
Unit tests for orchestrator.web_agent.

Mocks the module-level Tavily client (_client) rather than hitting the
real Tavily API. Live integration already verified manually. These
tests cover our own response-formatting logic: combining the
synthesized answer with source snippets, and handling errors/empty
results gracefully.
"""

import pytest
from unittest.mock import AsyncMock, patch

from orchestrator.web_agent import call_web_agent


@pytest.mark.asyncio
async def test_call_web_agent_formats_answer_and_sources():
    fake_response = {
        "answer": "Anthropic's latest model is Claude Sonnet 5.",
        "results": [
            {
                "title": "Anthropic News",
                "url": "https://anthropic.com/news",
                "content": "Details about the release.",
            }
        ],
    }
    with patch(
        "orchestrator.web_agent._client.search",
        new=AsyncMock(return_value=fake_response),
    ):
        result = await call_web_agent("latest Claude model")

    assert "Summary: Anthropic's latest model is Claude Sonnet 5." in result
    assert "Anthropic News" in result
    assert "https://anthropic.com/news" in result


@pytest.mark.asyncio
async def test_call_web_agent_handles_no_results():
    with patch(
        "orchestrator.web_agent._client.search",
        new=AsyncMock(return_value={"answer": None, "results": []}),
    ):
        result = await call_web_agent("something obscure")

    assert "No web results found" in result


@pytest.mark.asyncio
async def test_call_web_agent_raises_runtime_error_on_api_failure():
    with patch(
        "orchestrator.web_agent._client.search",
        new=AsyncMock(side_effect=ConnectionError("timeout")),
    ):
        with pytest.raises(RuntimeError, match="Web research failed"):
            await call_web_agent("anything")
