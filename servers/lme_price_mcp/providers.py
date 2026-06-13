from __future__ import annotations

import csv
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from project_env import load_dotenv


ALIASES = {
    "li": "lithium",
    "锂": "lithium",
    "锂矿": "lithium",
    "lithium hydroxide": "lithium",
    "cu": "copper",
    "铜": "copper",
    "zn": "zinc",
    "锌": "zinc",
    "ni": "nickel",
    "镍": "nickel",
    "iron ore": "iron_ore",
    "铁矿石": "iron_ore",
}


def build_price_provider(data_dir: str | Path | None = None) -> "HybridPriceProvider":
    load_dotenv()
    return HybridPriceProvider(data_dir)


class HybridPriceProvider:
    """Price provider that prefers configured live/manual sources and falls back to fixtures."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.mode = os.getenv("PRICE_MODE") or ("live" if _live_enabled() else "fixture")
        self.fixture = FixturePriceProvider(data_dir)
        self.manual = CsvPriceProvider(Path(os.getenv("PRICE_CSV_PATH"))) if os.getenv("PRICE_CSV_PATH") else None
        self.http = HttpPriceProvider(os.getenv("PRICE_API_URL")) if os.getenv("PRICE_API_URL") else None

    def get_price(self, commodity: str, date_value: str | None = None) -> dict[str, Any]:
        if self.mode == "fixture":
            return self.fixture.get_price(commodity=commodity, date_value=date_value)
        for provider in [self.manual, self.http]:
            if provider is None:
                continue
            result = provider.get_price(commodity=commodity, date_value=date_value)
            if "error" not in result or self.mode == "live":
                return result
        fixture = self.fixture.get_price(commodity=commodity, date_value=date_value)
        fixture["fallback_reason"] = {
            "code": "LIVE_PRICE_UNAVAILABLE",
            "message": "No configured live/manual price source returned a usable result.",
        }
        return fixture

    def get_trend(self, commodity: str, days: int = 30) -> dict[str, Any]:
        if self.mode == "fixture":
            return self.fixture.get_trend(commodity=commodity, days=days)
        for provider in [self.manual, self.http]:
            if provider is None:
                continue
            result = provider.get_trend(commodity=commodity, days=days)
            if "error" not in result or self.mode == "live":
                return result
        fixture = self.fixture.get_trend(commodity=commodity, days=days)
        fixture["fallback_reason"] = {
            "code": "LIVE_PRICE_UNAVAILABLE",
            "message": "No configured live/manual price source returned a usable result.",
        }
        return fixture


class CsvPriceProvider:
    def __init__(self, price_path: Path) -> None:
        self.price_path = price_path
        self._rows = _load_csv_rows(price_path, source_label="manual_csv")

    def get_price(self, commodity: str, date_value: str | None = None) -> dict[str, Any]:
        return _get_price_from_rows(self._rows, commodity, date_value, "manual_csv")

    def get_trend(self, commodity: str, days: int = 30) -> dict[str, Any]:
        return _get_trend_from_rows(self._rows, commodity, days, "manual_csv")


class HttpPriceProvider:
    """Generic JSON price API adapter.

    PRICE_API_URL may include {commodity}, {date}, and {days} placeholders.
    The response can be either a single object or a list of observations with fields:
    date, commodity, price, currency, unit, source_url.
    """

    def __init__(self, api_url_template: str | None) -> None:
        if not api_url_template:
            raise ValueError("api_url_template is required")
        self.api_url_template = api_url_template
        self.timeout = float(os.getenv("HTTP_TIMEOUT_SECONDS", "15"))
        self.retries = int(os.getenv("HTTP_RETRIES", "2"))

    def get_price(self, commodity: str, date_value: str | None = None) -> dict[str, Any]:
        normalized = normalize_commodity(commodity)
        target_date = date_value or date.today().isoformat()
        url = self._build_url(normalized, target_date, days=1)
        data = self._fetch_json(url)
        if "error" in data:
            return data
        rows = _json_to_rows(data, default_commodity=normalized, source_url=url)
        return _get_price_from_rows(rows, normalized, target_date, "live:http")

    def get_trend(self, commodity: str, days: int = 30) -> dict[str, Any]:
        normalized = normalize_commodity(commodity)
        url = self._build_url(normalized, date.today().isoformat(), days=days)
        data = self._fetch_json(url)
        if "error" in data:
            return data
        rows = _json_to_rows(data, default_commodity=normalized, source_url=url)
        return _get_trend_from_rows(rows, normalized, days, "live:http")

    def _build_url(self, commodity: str, date_value: str, days: int) -> str:
        return self.api_url_template.format(
            commodity=urllib.parse.quote(commodity),
            date=urllib.parse.quote(date_value),
            days=days,
        )

    def _fetch_json(self, url: str) -> dict[str, Any] | list[Any]:
        last_error: Exception | None = None
        for attempt in range(max(self.retries, 0) + 1):
            try:
                request = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": os.getenv(
                            "HTTP_USER_AGENT",
                            "Mozilla/5.0 (compatible; mining-daily-mcp-agent/0.1; +https://example.local)",
                        ),
                        "Accept": "application/json,text/csv;q=0.9,*/*;q=0.8",
                    },
                )
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.loads(response.read().decode("utf-8", errors="replace"))
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.4 * (attempt + 1))
        return {
            "error": {
                "code": "PRICE_API_FAILED",
                "message": f"Price API request failed for {url}: {last_error}",
            }
        }


class FixturePriceProvider:
    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.data_dir = _resolve_data_dir(data_dir)
        self.price_path = self.data_dir / "prices.csv"
        self._rows = _load_csv_rows(self.price_path, source_label="fixture:prices.csv")

    def get_price(self, commodity: str, date_value: str | None = None) -> dict[str, Any]:
        return _get_price_from_rows(self._rows, commodity, date_value, "fixture:prices.csv")

    def get_trend(self, commodity: str, days: int = 30) -> dict[str, Any]:
        return _get_trend_from_rows(self._rows, commodity, days, "fixture:prices.csv")


def normalize_commodity(value: str) -> str:
    normalized = value.strip().lower().replace("-", " ").replace("_", " ")
    if normalized in ALIASES:
        return ALIASES[normalized]
    if normalized == "iron ore":
        return "iron_ore"
    return normalized.replace(" ", "_")


def _parse_date(value: str | None) -> date:
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def _error(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def _live_enabled() -> bool:
    return os.getenv("LIVE_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


def _load_csv_rows(price_path: Path, source_label: str) -> list[dict[str, Any]]:
    if not price_path.exists():
        raise FileNotFoundError(f"price CSV not found: {price_path}")
    rows: list[dict[str, Any]] = []
    with price_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows.append(
                {
                    "date": _parse_date(row["date"]),
                    "commodity": normalize_commodity(row["commodity"]),
                    "price": float(row["price"]),
                    "currency": row.get("currency") or "USD",
                    "unit": row.get("unit") or "t",
                    "source": row.get("source") or source_label,
                    "source_url": row.get("source_url") or "",
                }
            )
    return rows


def _get_price_from_rows(
    source_rows: list[dict[str, Any]], commodity: str, date_value: str | None, source_label: str
) -> dict[str, Any]:
    normalized = normalize_commodity(commodity)
    rows = [row for row in source_rows if row["commodity"] == normalized]
    if not rows:
        return _error("COMMODITY_NOT_FOUND", f"No price for commodity: {commodity}")
    target = _parse_date(date_value) if date_value else max(row["date"] for row in rows)
    eligible = [row for row in rows if row["date"] <= target]
    if not eligible:
        return _error("PRICE_NOT_FOUND", f"No price found before or on {target.isoformat()}.")
    row = max(eligible, key=lambda item: item["date"])
    return {
        "commodity": normalized,
        "date": row["date"].isoformat(),
        "price": row["price"],
        "currency": row["currency"],
        "unit": row["unit"],
        "source": row.get("source") or source_label,
        "source_url": row.get("source_url") or "",
    }


def _get_trend_from_rows(
    source_rows: list[dict[str, Any]], commodity: str, days: int, source_label: str
) -> dict[str, Any]:
    normalized = normalize_commodity(commodity)
    rows = sorted([row for row in source_rows if row["commodity"] == normalized], key=lambda row: row["date"])
    if len(rows) < 2:
        return _error("TREND_UNAVAILABLE", f"Not enough prices for commodity: {commodity}")
    reference_date = rows[-1]["date"]
    min_date = reference_date - timedelta(days=max(days, 1))
    window = [row for row in rows if row["date"] >= min_date]
    if len(window) < 2:
        window = rows[-2:]
    start = window[0]
    end = window[-1]
    change_abs = end["price"] - start["price"]
    change_pct = 0.0 if start["price"] == 0 else change_abs / start["price"] * 100
    direction = "flat"
    if change_pct > 0.5:
        direction = "up"
    elif change_pct < -0.5:
        direction = "down"
    return {
        "commodity": normalized,
        "days": days,
        "start_date": start["date"].isoformat(),
        "end_date": end["date"].isoformat(),
        "start_price": start["price"],
        "end_price": end["price"],
        "change_abs": round(change_abs, 4),
        "change_pct": round(change_pct, 2),
        "direction": direction,
        "currency": end["currency"],
        "unit": end["unit"],
        "observations": [
            {"date": row["date"].isoformat(), "price": row["price"]} for row in window
        ],
        "source": source_label,
        "source_url": end.get("source_url") or "",
    }


def _json_to_rows(
    data: dict[str, Any] | list[Any], default_commodity: str, source_url: str
) -> list[dict[str, Any]]:
    raw_rows = data if isinstance(data, list) else data.get("items") or data.get("observations") or [data]
    rows: list[dict[str, Any]] = []
    for row in raw_rows:
        if not isinstance(row, dict) or "price" not in row:
            continue
        rows.append(
            {
                "date": _parse_date(row.get("date")),
                "commodity": normalize_commodity(row.get("commodity") or default_commodity),
                "price": float(row["price"]),
                "currency": row.get("currency") or "USD",
                "unit": row.get("unit") or "t",
                "source": row.get("source") or "live:http",
                "source_url": row.get("source_url") or source_url,
            }
        )
    return rows


def _resolve_data_dir(data_dir: str | Path | None) -> Path:
    if data_dir:
        path = Path(data_dir)
    else:
        path = Path(os.getenv("DATA_DIR", "data/fixtures"))
    if path.is_absolute():
        return path
    cwd_path = Path.cwd() / path
    if cwd_path.exists():
        return cwd_path
    return Path(__file__).resolve().parents[2] / path
