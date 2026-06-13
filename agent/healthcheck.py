from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from agent.mcp_client import LocalToolClient
from project_env import load_dotenv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check configured mining daily data sources.")
    parser.add_argument("--query", default="Pilbara lithium")
    parser.add_argument("--commodity", default="lithium")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--data-dir", default=os.getenv("DATA_DIR", "data/fixtures"))
    parser.add_argument("--pdf-url", default=os.getenv("RESOURCE_PDF_URL", "fixture://reports/pilbara-ni-43-101"))
    return parser


def main() -> None:
    load_dotenv()
    args = build_parser().parse_args()
    client = LocalToolClient(Path(args.data_dir))
    payload: dict[str, Any] = {
        "news": client.search_news(args.query, args.days),
        "resources": client.extract_resources(args.pdf_url),
        "price": client.get_price(args.commodity),
        "trend": client.get_trend(args.commodity, 30),
        "env": {
            "LIVE_MODE": os.getenv("LIVE_MODE"),
            "NEWS_MODE": os.getenv("NEWS_MODE"),
            "PRICE_MODE": os.getenv("PRICE_MODE"),
            "NEWS_RSS_URLS": os.getenv("NEWS_RSS_URLS"),
            "PRICE_CSV_PATH": os.getenv("PRICE_CSV_PATH"),
            "PRICE_API_URL": os.getenv("PRICE_API_URL"),
            "RESOURCE_PDF_URL": os.getenv("RESOURCE_PDF_URL"),
        },
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
