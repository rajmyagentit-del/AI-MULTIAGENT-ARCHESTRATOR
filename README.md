# AI Multi-Agent Orchestrator

A LangGraph-based supervisor that coordinates three independent AI specialists — a SQL database agent, a document RAG agent, and a live web research agent — routing each question to whichever specialist(s) it actually needs, and synthesizing their results into one answer.

**Live demo:** https://ai-multiagent-archestrator.onrender.com/demo
**MCP endpoint:** https://ai-multiagent-archestrator.onrender.com/mcp

This is Project 3 in a portfolio series. The two specialists it coordinates are themselves independently deployed, production projects:
- [`ai-sql-agent-mcp`](https://github.com/rajmyagentit-del/ai-sql-agent-mcp) — Project 1
- [`ai-document-mcp`](https://github.com/rajmyagentit-del/ai-document-mcp) — Project 2

---

## Why this project

Most "agent" demos show a single LLM calling a single tool. This project demonstrates something closer to production multi-agent systems: a supervisor that must *decide which of several independent, already-deployed services to call*, potentially several at once, and combine their results honestly — including saying when a specialist's answer is incomplete or low-confidence, rather than papering over gaps.


## Architecture

1. A user question comes in to the **LangGraph Supervisor** (Claude Sonnet 5).
2. The supervisor decides which specialist(s) the question needs, and calls one, several, or none:
   - `ask_database` -> a live MCP call to **ai-sql-agent-mcp** (Project 1, deployed independently on Render)
   - `search_documents` -> a live MCP call to **ai-document-mcp** (Project 2, deployed independently on Render)
   - `search_web` -> a live call to the **Tavily Search API**
3. Specialist results return to the supervisor, which synthesizes one final answer -- citing which specialist(s) it used, and flagging low-confidence or missing information honestly rather than guessing.

The supervisor and both MCP client wrappers run in *this* service. `ask_database` and `search_documents` are thin clients making real network calls to two other, independently deployed services -- not local functions pretending to be remote.

## Features

- **Multi-specialist fan-out**: a single question can trigger multiple specialists in parallel (e.g. "what do our documents say about X, and what's the latest news on X?" correctly calls both `search_documents` and `search_web` in one supervisor turn — verified live, see Proof section below).
- **Judgment, not blind routing**: the supervisor recognizes when a question needs *no* specialist at all and answers directly from general knowledge (verified live — see Proof section).
- **Triple exposure**: the same orchestration logic is reachable three ways — as an MCP tool (`orchestrate`), as a REST endpoint (`/demo/query`), and via a browser demo (`/demo`) — all sharing one code path so they can't drift out of sync.
- **Graceful degradation**: if a specialist errors or returns low-confidence results, the supervisor says so explicitly rather than fabricating certainty.

## Live demo -- real, unedited output

Three real queries run against the live public deployment:

**1. Document specialist, correctly scoped**

> "What does the Q3 report say about Acme Corp?"

Routed to `search_documents` only. Returned the real management-fee figures from the ingested report, and honestly flagged low retrieval confidence rather than overstating certainty.

![Document specialist example](docs/demo-screenshots/01-document-specialist.png)

**2. SQL specialist, with an honest limitation**

> "What tables are in the database?"

Routed to `ask_database`. Correctly identified the `customers` and `orders` tables, and explicitly explained what it could not determine (no system-catalog access) instead of guessing.

![SQL specialist honest limitation example](docs/demo-screenshots/02-sql-specialist-honest-limitation.png)

**3. No specialist needed**

> "what is AI"

Correctly recognized this needed no tool call at all, answered directly, and proactively offered to use a specialist if the question had actually been about the org's own data.

![No specialist needed example](docs/demo-screenshots/03-no-specialist-needed.png)

## Tech stack

| Layer | Technology |
|---|---|
| Orchestration | LangGraph (supervisor + tool-calling graph) |
| LLM | Claude Sonnet 5 (Anthropic API) |
| Specialist transport | MCP (Model Context Protocol) over streamable HTTP |
| Web research | Tavily Search API |
| Server | FastMCP 3 (MCP server + custom REST/HTML routes) |
| Testing | pytest, pytest-asyncio, unittest.mock |
| CI | GitHub Actions |
| Deployment | Docker on Render (free tier) |

## Project structure

```
orchestrator/
  config.py        - centralized, validated settings (pydantic-settings)
  mcp_clients.py    - MCP client wrappers for ai-sql-agent-mcp and ai-document-mcp
  web_agent.py       - Tavily-based web research specialist
  graph.py             - LangGraph supervisor + tool-calling loop
  server.py             - FastMCP server: orchestrate tool, /health, /demo, /demo/query
tests/                     - pytest suite, all external calls mocked
.github/workflows/ci.yml   - runs the test suite on every push and PR
Dockerfile
```

## Running locally

Requires Python 3.12+ and API keys for Anthropic and Tavily.

```bash
git clone https://github.com/rajmyagentit-del/AI-MULTIAGENT-ARCHESTRATOR.git
cd AI-MULTIAGENT-ARCHESTRATOR
pip install -r requirements.txt
cp .env.example .env   # then fill in your real keys
python orchestrator/server.py
```

The server starts on `http://localhost:8000`. Visit `/demo` in a browser, or:

```bash
curl -X POST http://localhost:8000/demo/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How many customers do we have?"}'
```

## Running with Docker

```bash
docker build -t ai-multiagent-orchestrator .
docker run -p 8000:8000 --env-file .env ai-multiagent-orchestrator
```

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `TAVILY_API_KEY` | Yes | Tavily search API key |
| `SQL_AGENT_MCP_URL` | No | Defaults to the live Project 1 deployment |
| `DOCUMENT_AGENT_MCP_URL` | No | Defaults to the live Project 2 deployment |
| `PORT` | No | Defaults to 8000; Render sets this automatically |

## Testing

```bash
python -m pytest tests/ -v
```

10 tests, all passing, all external services (Anthropic, Tavily, both MCP servers) mocked -- CI runs standalone with no real secrets required. Tests cover:
- Correct MCP tool-call argument names (regression coverage for two real bugs found during development -- see Engineering Notes)
- Error handling when a specialist fails or is unreachable
- The supervisor's routing decision logic
- The full supervisor<->tools loop end-to-end (mocked LLM + mocked specialist)

## Deployment

Deployed on [Render](https://render.com) via the included `Dockerfile`, free tier. Auto-deploys on every push to `main`. Note: free tier spins down on inactivity -- the first request after idle time can take up to ~50 seconds while it cold-starts.

## Engineering notes: real problems hit and fixed

Documenting these because working through them honestly is more useful than pretending the build was frictionless:

- **MCP client library version gap**: the initial `mcp` SDK pin (1.1.3) predated the `streamable_http` client transport needed to actually call the two live specialist servers. Diagnosed via a real `ModuleNotFoundError`, resolved by upgrading to 1.29.0 (not the newest 2.0.0 major, which introduced its own unrelated dependency conflicts).
- **Wrong tool parameter name**: assumed `ask_database`'s parameter was `query`; the real signature uses `question`. Found via a live test against the deployed server, confirmed against the Project 1 source, fixed, and locked in with a regression test.
- **Claude Sonnet 5 content shape**: with extended thinking enabled by default, message content is a list of typed blocks (thinking plus text), not a plain string like older models. The first live deployment leaked a raw thinking block into the public /demo/query response. Fixed with an explicit text-extraction helper and verified on the redeployed live service.
- **Unused dependency causing a real conflict chain**: fastapi and uvicorn were added early on a guess, before settling on the FastMCP framework pattern. Neither was ever actually imported. They silently pinned starlette too old for fastmcp to install, causing a multi-layer version conflict. Root-caused by checking actual imports rather than chasing version numbers indefinitely, then removed entirely.
- **CI failing on every historical commit**: config.py's fail-fast validation (a deliberate design choice) correctly blocked test collection in CI because no secrets exist there. Fixed with obviously-fake placeholder env vars in the workflow, safe because every test mocks the real API calls.

## License

MIT -- see `LICENSE`.

## Credits

Built on top of two other original projects in this portfolio series (`ai-sql-agent-mcp`, `ai-document-mcp`), coordinated via [LangGraph](https://github.com/langchain-ai/langgraph), [Anthropic's Claude API](https://www.anthropic.com), [Tavily](https://tavily.com), and [FastMCP](https://gofastmcp.com).
