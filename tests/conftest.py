from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def deterministic_test_environment(monkeypatch) -> None:
    """Keep unit tests deterministic even when local .env enables live services."""

    monkeypatch.setenv("LLM_ENABLED", "false")
    monkeypatch.setenv("LIVE_MODE", "false")
    monkeypatch.setenv("NEWS_MODE", "fixture")
    monkeypatch.setenv("PRICE_MODE", "fixture")
    monkeypatch.delenv("RESOURCE_PDF_URL", raising=False)
    monkeypatch.delenv("PRICE_CSV_PATH", raising=False)
    monkeypatch.delenv("PRICE_API_URL", raising=False)
