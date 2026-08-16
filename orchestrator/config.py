"""
Centralized, validated configuration for the multi-agent orchestrator.

Every other module imports `settings` from here instead of calling
os.getenv() directly. This gives us two things a scattered approach
doesn't: (1) startup-time validation -- a missing required key fails
loudly and immediately, not three requests deep into a run, and
(2) one place to look when adding a new external dependency.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Reasoning model ---
    anthropic_api_key: str

    # --- Web research specialist ---
    tavily_api_key: str

    # --- Specialist MCP servers (Projects 1 & 2, already live) ---
    sql_agent_mcp_url: str = "https://ai-sql-agent-mcp.onrender.com/mcp"
    document_agent_mcp_url: str = "https://ai-document-mcp.onrender.com/mcp"

    # --- Server ---
    # Render injects PORT at deploy time; 8000 is the local/Codespaces default.
    port: int = 8000

    # --- Model choice ---
    # Centralized here so swapping models later is a one-line change,
    # not a grep-and-replace across every node.
    claude_model: str = "claude-sonnet-5"


settings = Settings()
