"""Free web search tool using DuckDuckGo (ddgs library, no API key needed)."""
from __future__ import annotations

import logging

from tools.registry import Tool

log = logging.getLogger(__name__)


def _web_search(query: str, max_results: int = 5) -> str:
    """Search the web via DuckDuckGo and return formatted results."""
    try:
        from ddgs import DDGS

        with DDGS() as ddg:
            results = list(ddg.text(query, max_results=max_results))

        if not results:
            return f"No results found for: {query}"

        formatted = []
        for i, r in enumerate(results, 1):
            title = r.get("title", "")
            body = r.get("body", "")
            href = r.get("href", "")
            formatted.append(f"{i}. **{title}**\n   {body}\n   URL: {href}")

        return "\n\n".join(formatted)

    except ImportError:
        return "Error: ddgs library not installed. Run: pip install ddgs"
    except Exception as e:
        log.error("Web search failed: %s", e)
        return f"Web search error: {e}"


WEB_SEARCH_TOOL = Tool(
    name="web_search",
    description=(
        "Search the web using DuckDuckGo. Use this when you need current "
        "information, facts, prices, news, research findings, or anything "
        "you're not confident about from your training data."
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to look up on the web.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default 5).",
                "default": 5,
            },
        },
        "required": ["query"],
    },
    function=_web_search,
)
