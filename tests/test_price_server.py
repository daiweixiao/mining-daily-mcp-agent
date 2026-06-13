from pathlib import Path

from servers.lme_price_mcp.providers import CsvPriceProvider, FixturePriceProvider


def test_get_latest_lithium_price() -> None:
    result = FixturePriceProvider().get_price("锂")

    assert result["commodity"] == "lithium"
    assert result["price"] == 14300
    assert result["date"] == "2026-06-12"


def test_get_lithium_trend() -> None:
    result = FixturePriceProvider().get_trend("lithium", days=30)

    assert result["direction"] == "up"
    assert result["change_pct"] > 0
    assert len(result["observations"]) >= 2


def test_manual_csv_price_provider(tmp_path: Path) -> None:
    csv_path = tmp_path / "prices.csv"
    csv_path.write_text(
        "date,commodity,price,currency,unit,source,source_url\n"
        "2026-06-01,lithium,100,USD,t,test,https://example.com/1\n"
        "2026-06-12,lithium,120,USD,t,test,https://example.com/2\n",
        encoding="utf-8",
    )

    provider = CsvPriceProvider(csv_path)
    price = provider.get_price("lithium")
    trend = provider.get_trend("lithium", days=30)

    assert price["price"] == 120
    assert trend["direction"] == "up"
