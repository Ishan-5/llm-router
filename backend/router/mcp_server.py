"""
MCP gateway for routewise — exposes the router as an MCP tool server.

Agents (Claude Desktop, Cursor, etc.) connect via stdio and get one tool:
  ask_routewise(query, override_tier?, threshold?)

The tool runs the full routing pipeline locally:
  guardrails → web search → cache → classifier → call_with_failover

No HTTP round-trip to the FastAPI server. No auth required — this is a
local process tool, not a public endpoint.

Usage (stdio transport, standard MCP):
  python -m router.mcp_server

Claude Desktop config (~/.claude/claude_desktop_config.json):
  {
    "mcpServers": {
      "routewise": {
        "command": "python",
        "args": ["-m", "router.mcp_server"],
        "cwd": "/path/to/llm-router/backend"
      }
    }
  }
"""

import sys
import os
import logging

# ensure src/ is on path for predict_difficulty
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

from router.guardrails import is_prompt_injection, needs_web_search
from router.cache import check_cache, add_to_cache
from router.classifier import get_tier
from router.rate_limiter import call_with_failover, AllTiersFailedError
from router.config import TAVILY_API_KEY

log = logging.getLogger("routewise.mcp")
logging.basicConfig(level=logging.WARNING)

server = Server("routewise")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="ask_routewise",
            description=(
                "Route a query through the cost-aware LLM router. "
                "Automatically selects cheap/mid/frontier model tier based on query difficulty. "
                "Checks semantic cache, runs web search for time-sensitive queries, "
                "and fails over across providers on errors."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The question or task to route.",
                    },
                    "override_tier": {
                        "type": "string",
                        "enum": ["cheap", "mid", "frontier"],
                        "description": "Force a specific tier instead of auto-routing.",
                    },
                    "threshold": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 2.0,
                        "description": "Routing sensitivity: 0=economy (more cheap), 1=balanced, 2=quality (more frontier).",
                    },
                },
                "required": ["query"],
            },
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name != "ask_routewise":
        raise ValueError(f"Unknown tool: {name}")

    query = arguments.get("query", "").strip()
    if not query:
        return [types.TextContent(type="text", text="Error: query cannot be empty")]
    if len(query) > 1000:
        return [types.TextContent(type="text", text="Error: query exceeds 1000 characters")]

    if is_prompt_injection(query):
        return [types.TextContent(type="text", text="Error: prompt injection detected")]

    override_tier = arguments.get("override_tier")
    threshold = arguments.get("threshold", 1.0)

    # web search for time-sensitive queries
    if needs_web_search(query) and TAVILY_API_KEY:
        try:
            import httpx
            resp = httpx.post(
                "https://api.tavily.com/search",
                json={"api_key": TAVILY_API_KEY, "query": query, "search_depth": "advanced", "max_results": 5, "include_answer": True},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            answer = data.get("answer") or "\n\n".join(r["content"][:300] for r in data.get("results", [])[:3])
            return [types.TextContent(type="text", text=f"[web] {answer}")]
        except Exception as e:
            log.warning("Web search failed, falling through to model routing: %s", e)

    # cache check
    cached = check_cache(query)
    if cached:
        return [types.TextContent(
            type="text",
            text=f"[cache:{cached['tier']}] {cached['response']}",
        )]

    # classify + route
    difficulty_score, tier, _, _ = get_tier(query, threshold)
    routing_tier = override_tier if override_tier else tier

    try:
        result = call_with_failover(routing_tier, query)
    except AllTiersFailedError as e:
        return [types.TextContent(type="text", text=f"Error: all model tiers failed — {e}")]

    add_to_cache(query, result["text"], result["tier"], result["model_id"], result["cost_usd"], result["input_tokens"], result["output_tokens"])

    meta = (
        f"[{result['tier']}"
        + (f"←{result['intended_tier']}" if result.get("fallback_used") else "")
        + f" score={difficulty_score:.2f} ${result['cost_usd']:.5f}]"
    )
    return [types.TextContent(type="text", text=f"{meta}\n{result['text']}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
