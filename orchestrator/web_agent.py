"""
Web research specialist: answers questions needing current, external
information that neither the SQL database nor ingested documents would
have -- e.g. recent news, current rates, anything time-sensitive.

Uses Tavily's AsyncTavilyClient directly (native async, no thread-pool
workaround needed) for consistency with the rest of this async codebase.
"""

import logging

from tavily import AsyncTavilyClient

from orchestrator.config import settings

logger = logging.getLogger(__name__)

_client = AsyncTavilyClient(api_key=settings.tavily_api_key)


async def call_web_agent(query: str) -> str:
    """
    Run a live web search via Tavily and return a plain-text summary:
    Tavily's synthesized answer (when available) followed by a few
    source snippets, so the supervisor has both a quick answer and
    grounding detail to reason over.
    """
    try:
        response = await _client.search(
            query=query,
            max_results=5,
            include_answer=True,
            search_depth="advanced",
        )
    except Exception as exc:
        logger.error("Tavily search failed for query %r: %s", query, exc)
        raise RuntimeError(f"Web research failed for '{query}': {exc}") from exc

    parts = []

    answer = response.get("answer")
    if answer:
        parts.append(f"Summary: {answer}")

    results = response.get("results", [])
    if results:
        parts.append("Sources:")
        for r in results[:5]:
            title = r.get("title", "Untitled")
            url = r.get("url", "")
            content = (r.get("content") or "")[:300]
            parts.append(f"- {title} ({url}): {content}")

    if not parts:
        return f"No web results found for '{query}'."

    return "\n".join(parts)
