"""AI Multi-Agent Orchestrator MCP Server.

Exposes one MCP tool, `orchestrate`, that routes a natural-language
question through the LangGraph supervisor to one or more of three live
specialists (SQL agent, document RAG agent, web research agent) and
returns a synthesized answer.

Also exposes a browser-friendly live demo at /demo (HTML page) and
/demo/query (JSON endpoint) on top of the same orchestration logic
used by the MCP tool, plus /health for uptime checks.
"""

from __future__ import annotations

import os

from fastmcp import FastMCP
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from orchestrator.graph import orchestrator_graph

mcp = FastMCP(name="ai-multiagent-orchestrator")


def _extract_text(content) -> str:
    """Claude's message content is a plain string for simple responses,
    but a list of typed blocks (thinking, text, tool_use, etc.) when
    extended thinking is involved -- true by default for Claude Sonnet 5.
    This pulls out only the actual answer text, discarding thinking
    blocks so internal reasoning traces never leak into a public answer."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "\n".join(text_parts).strip()
    return str(content)


async def _run_orchestration(question: str) -> dict:
    """Shared logic: runs a question through the graph, returns the final
    answer plus which specialist tools were actually used -- used by both
    the MCP tool and the /demo/query REST endpoint so they can never
    drift out of sync with each other."""
    result = await orchestrator_graph.ainvoke(
        {"messages": [HumanMessage(content=question)]}
    )
    messages = result["messages"]

    specialists_used = []
    for m in messages:
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            for tc in m.tool_calls:
                if tc["name"] not in specialists_used:
                    specialists_used.append(tc["name"])

    final_answer = _extract_text(messages[-1].content)

    return {
        "answer": final_answer,
        "specialists_used": specialists_used,
    }


@mcp.tool()
async def orchestrate(question: str) -> dict:
    """Answer a question by routing it to one or more specialist agents:
    a SQL database agent, a document RAG agent, and a web research agent.
    Automatically determines which specialist(s) the question needs.

    Args:
        question: A natural-language question. May require data from the
            database, ingested documents, the live web, or a combination.
    """
    return await _run_orchestration(question)


@mcp.custom_route("/health", methods=["GET"])
async def health(request):
    from starlette.responses import JSONResponse
    return JSONResponse({"status": "ok"})


DEMO_HTML = """
<!DOCTYPE html>
<html>
<head>
<title>AI Multi-Agent Orchestrator</title>
<style>
  body { font-family: -apple-system, sans-serif; max-width: 720px; margin: 40px auto; padding: 0 20px; background: #0d1117; color: #e6edf3; }
  h1 { font-size: 1.4em; }
  .sub { color: #8b949e; margin-bottom: 24px; font-size: 0.9em; }
  input { width: 100%; padding: 12px; font-size: 1em; border-radius: 8px; border: 1px solid #30363d; background: #161b22; color: #e6edf3; box-sizing: border-box; }
  button { margin-top: 10px; padding: 10px 20px; font-size: 1em; border-radius: 8px; border: none; background: #238636; color: white; cursor: pointer; }
  button:disabled { background: #30363d; cursor: not-allowed; }
  #output { margin-top: 24px; white-space: pre-wrap; line-height: 1.5; }
  .badges { margin-bottom: 12px; }
  .badge { display: inline-block; background: #1f6feb; color: white; padding: 3px 10px; border-radius: 12px; font-size: 0.8em; margin-right: 6px; }
  .loading { color: #8b949e; font-style: italic; }
</style>
</head>
<body>
<h1>AI Multi-Agent Orchestrator</h1>
<div class="sub">Ask a question -- it may need the SQL database, ingested documents, live web search, or a combination. Watch which specialists get used.</div>
<input id="q" placeholder="e.g. How many customers do we have, and what's the latest AI news?" />
<button id="btn">Ask</button>
<div id="output"></div>

<script>
const input = document.getElementById('q');
const button = document.getElementById('btn');
const output = document.getElementById('output');

async function runQuery() {
  const question = input.value.trim();
  if (!question) return;
  button.disabled = true;
  output.innerHTML = '<div class="loading">Routing to specialist(s)... (first request may take up to a minute if servers are cold-starting)</div>';
  try {
    const res = await fetch('/demo/query', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({question})
    });
    const data = await res.json();
    renderResult(data);
  } catch (e) {
    output.innerHTML = '<div style="color:#f85149;">Error: ' + escapeHtml(String(e)) + '</div>';
  }
  button.disabled = false;
}

function renderResult(data) {
  let html = '';
  if (data.specialists_used && data.specialists_used.length > 0) {
    html += '<div class="badges">';
    for (const s of data.specialists_used) {
      html += '<span class="badge">' + escapeHtml(s) + '</span>';
    }
    html += '</div>';
  }
  html += '<div>' + escapeHtml(data.answer || data.error || 'No answer returned.') + '</div>';
  output.innerHTML = html;
}

function escapeHtml(s) {
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

button.addEventListener('click', runQuery);
input.addEventListener('keydown', (e) => { if (e.key === 'Enter') runQuery(); });
</script>
</body>
</html>
"""


@mcp.custom_route("/demo", methods=["GET"])
async def demo_page(request):
    from starlette.responses import HTMLResponse
    return HTMLResponse(DEMO_HTML)


@mcp.custom_route("/demo/query", methods=["POST"])
async def demo_query(request):
    from starlette.responses import JSONResponse
    body = await request.json()
    question = body.get("question", "")
    if not question:
        return JSONResponse({"error": "question is required"}, status_code=400)
    try:
        result = await _run_orchestration(question)
        return JSONResponse(result)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    mcp.run(transport="http", host="0.0.0.0", port=port)
