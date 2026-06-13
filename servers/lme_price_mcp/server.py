from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from project_env import load_dotenv
from servers.lme_price_mcp.providers import build_price_provider


def get_price(
    commodity: str, date: str | None = None, data_dir: str | Path | None = None
) -> dict[str, Any]:
    load_dotenv()
    return build_price_provider(data_dir).get_price(commodity=commodity, date_value=date)


def get_trend(commodity: str, days: int = 30, data_dir: str | Path | None = None) -> dict[str, Any]:
    load_dotenv()
    return build_price_provider(data_dir).get_trend(commodity=commodity, days=days)


def build_mcp_server() -> Any:
    load_dotenv()
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError("Install MCP dependencies with `pip install -e .`.") from exc

    data_dir = os.getenv("DATA_DIR", "data/fixtures")
    mcp = FastMCP("lme-price-mcp")

    @mcp.tool()
    def get_price(commodity: str, date: str | None = None) -> dict[str, Any]:
        """Get the latest or date-specific price for a commodity."""

        return build_price_provider(data_dir).get_price(commodity=commodity, date_value=date)

    @mcp.tool()
    def get_trend(commodity: str, days: int = 30) -> dict[str, Any]:
        """Get the price trend for a commodity over a day window."""

        return build_price_provider(data_dir).get_trend(commodity=commodity, days=days)

    return mcp


def main() -> None:
    build_mcp_server().run(transport="stdio")


if __name__ == "__main__":
    main()
