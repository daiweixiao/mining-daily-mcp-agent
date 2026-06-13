from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from agent.mcp_client import LocalToolClient, StdioMCPToolClient
from agent.orchestrator import MiningDailyAgent
from project_env import load_dotenv


DEFAULT_PROMPT = "给我生成一份关于Pilbara锂矿的今日简报"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a mining rights daily report.")
    parser.add_argument("prompt", nargs="?", default=DEFAULT_PROMPT)
    parser.add_argument(
        "--transport",
        choices=["local", "mcp"],
        default=os.getenv("AGENT_TRANSPORT", "local"),
        help="local uses fixture providers in-process; mcp calls the MCP stdio servers.",
    )
    parser.add_argument(
        "--data-dir",
        default=os.getenv("DATA_DIR", "data/fixtures"),
        help="Path to fixture data directory.",
    )
    parser.add_argument(
        "--output",
        help=(
            "Path to write the generated Markdown report. Defaults to "
            "reports/mining_daily_<timestamp>.md."
        ),
    )
    return parser


def main() -> None:
    _configure_stdout()
    load_dotenv()
    args = build_parser().parse_args()
    data_dir = Path(args.data_dir)
    client = StdioMCPToolClient(data_dir) if args.transport == "mcp" else LocalToolClient(data_dir)
    report = MiningDailyAgent(client).generate_report(args.prompt)
    output_path = _resolve_output_path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report + "\n", encoding="utf-8")
    print(report)
    print(f"\nSaved report to {output_path}", file=sys.stderr)


def _configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def _resolve_output_path(output: str | None) -> Path:
    if output:
        return Path(output)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return Path("reports") / f"mining_daily_{timestamp}.md"


if __name__ == "__main__":
    main()
