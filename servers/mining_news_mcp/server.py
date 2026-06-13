from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from project_env import load_dotenv
from servers.mining_news_mcp.providers import build_news_provider


def search(query: str, days: int = 7, data_dir: str | Path | None = None) -> dict[str, Any]:
    load_dotenv()
    return build_news_provider(data_dir).search(query=query, days=days)


def fetch_article(url: str, data_dir: str | Path | None = None) -> dict[str, Any]:
    load_dotenv()
    return build_news_provider(data_dir).fetch_article(url=url)


def build_mcp_server() -> Any:
    load_dotenv()
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError("Install MCP dependencies with `pip install -e .`.") from exc

    data_dir = os.getenv("DATA_DIR", "data/fixtures")
    mcp = FastMCP("mining-news-mcp")

    @mcp.tool()
    def search(query: str, days: int = 7) -> dict[str, Any]:
        """Search recent mining news by query and day window."""

        return build_news_provider(data_dir).search(query=query, days=days)

    @mcp.tool()
    def fetch_article(url: str) -> dict[str, Any]:
        """Fetch a full article by URL from the mining news corpus."""

        return build_news_provider(data_dir).fetch_article(url=url)

    return mcp


def main() -> None:
    build_mcp_server().run(transport="stdio")


if __name__ == "__main__":
    main()
