from __future__ import annotations

import sys
from pathlib import Path

from agent import cli


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = PROJECT_ROOT / "data" / "fixtures"
PROMPT = "Generate a Pilbara lithium daily report"


def test_cli_auto_saves_report(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_ENABLED", "false")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "agent.cli",
            "--transport",
            "local",
            "--data-dir",
            str(FIXTURE_DIR),
            PROMPT,
        ],
    )

    cli.main()

    reports = list((tmp_path / "reports").glob("mining_daily_*.md"))
    assert len(reports) == 1
    content = reports[0].read_text(encoding="utf-8")
    assert content.startswith("# Pilbara Lithium")
    assert "Indicated" in content

    captured = capsys.readouterr()
    assert "Saved report to" in captured.err


def test_cli_respects_explicit_output_path(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LLM_ENABLED", "false")
    output_path = tmp_path / "custom" / "daily.md"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "agent.cli",
            "--transport",
            "local",
            "--data-dir",
            str(FIXTURE_DIR),
            "--output",
            str(output_path),
            PROMPT,
        ],
    )

    cli.main()

    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8").startswith("# Pilbara Lithium")
    assert not (tmp_path / "reports").exists()
