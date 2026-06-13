from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from servers.lme_price_mcp.providers import build_price_provider
from servers.mineral_pdf_mcp.extractor import ResourceExtractor
from servers.mining_news_mcp.providers import build_news_provider
from project_env import load_dotenv


class LocalToolClient:
    """Deterministic in-process tool client used for tests and offline demos."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        load_dotenv()
        self.data_dir = Path(data_dir or os.getenv("DATA_DIR", "data/fixtures"))
        self.news = build_news_provider(self.data_dir)
        self.resources = ResourceExtractor(self.data_dir)
        self.prices = build_price_provider(self.data_dir)

    def search_news(self, query: str, days: int) -> dict[str, Any]:
        return self.news.search(query=query, days=days)

    def fetch_article(self, url: str) -> dict[str, Any]:
        return self.news.fetch_article(url=url)

    def extract_resources(self, pdf_url: str) -> dict[str, Any]:
        return self.resources.extract_resources(pdf_url=pdf_url)

    def get_price(self, commodity: str, date: str | None = None) -> dict[str, Any]:
        return self.prices.get_price(commodity=commodity, date_value=date)

    def get_trend(self, commodity: str, days: int) -> dict[str, Any]:
        return self.prices.get_trend(commodity=commodity, days=days)


class StdioMCPToolClient:
    """MCP stdio client. It starts each server on demand and calls one tool."""

    SERVER_MODULES = {
        "news": "servers.mining_news_mcp.server",
        "pdf": "servers.mineral_pdf_mcp.server",
        "price": "servers.lme_price_mcp.server",
    }

    def __init__(self, data_dir: str | Path | None = None) -> None:
        load_dotenv()
        self.data_dir = str(Path(data_dir or os.getenv("DATA_DIR", "data/fixtures")))

    def search_news(self, query: str, days: int) -> dict[str, Any]:
        return self._call("news", "search", {"query": query, "days": days})

    def fetch_article(self, url: str) -> dict[str, Any]:
        return self._call("news", "fetch_article", {"url": url})

    def extract_resources(self, pdf_url: str) -> dict[str, Any]:
        return self._call("pdf", "extract_resources", {"pdf_url": pdf_url})

    def get_price(self, commodity: str, date: str | None = None) -> dict[str, Any]:
        return self._call("price", "get_price", {"commodity": commodity, "date": date})

    def get_trend(self, commodity: str, days: int) -> dict[str, Any]:
        return self._call("price", "get_trend", {"commodity": commodity, "days": days})

    def _call(self, server_key: str, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return asyncio.run(self._call_async(server_key, tool_name, arguments))

    async def _call_async(
        self, server_key: str, tool_name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError as exc:
            raise RuntimeError(
                "MCP client dependencies are not installed. Run `pip install -e .` "
                "or use `--transport local` for the offline fixture demo."
            ) from exc

        env = os.environ.copy()
        env["DATA_DIR"] = self.data_dir
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", self.SERVER_MODULES[server_key]],
            env=env,
        )
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
        return _decode_mcp_result(result)


def _decode_mcp_result(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None) or getattr(
        result, "structured_content", None
    )
    if isinstance(structured, dict):
        return structured

    content = getattr(result, "content", None) or []
    for item in content:
        text = getattr(item, "text", None)
        if not text:
            continue
        try:
            decoded = json.loads(text)
            if isinstance(decoded, dict):
                return decoded
            return {"result": decoded}
        except json.JSONDecodeError:
            return {"text": text}
    return {"result": result.model_dump() if hasattr(result, "model_dump") else str(result)}
