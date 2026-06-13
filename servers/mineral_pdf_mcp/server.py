from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from project_env import load_dotenv
from servers.mineral_pdf_mcp.extractor import ResourceExtractor


def extract_resources(pdf_url: str, data_dir: str | Path | None = None) -> dict[str, Any]:
    load_dotenv()
    return ResourceExtractor(data_dir).extract_resources(pdf_url=pdf_url)


def build_mcp_server() -> Any:
    load_dotenv()
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise RuntimeError("Install MCP dependencies with `pip install -e .`.") from exc

    data_dir = os.getenv("DATA_DIR", "data/fixtures")
    mcp = FastMCP("mineral-pdf-mcp")

    @mcp.tool()
    def extract_resources(pdf_url: str) -> dict[str, Any]:
        """Extract NI 43-101 Indicated/Inferred resources from a report URL."""

        return ResourceExtractor(data_dir).extract_resources(pdf_url=pdf_url)

    return mcp


def main() -> None:
    build_mcp_server().run(transport="stdio")


if __name__ == "__main__":
    main()
