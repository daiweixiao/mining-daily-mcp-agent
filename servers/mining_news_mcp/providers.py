from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from project_env import load_dotenv


ALIASES = {
    "锂": "lithium",
    "锂矿": "lithium",
    "铜": "copper",
    "锌": "zinc",
    "镍": "nickel",
    "铁矿石": "iron ore",
}

DEFAULT_RSS_URLS = [
    "https://www.mining.com/feed/",
]


def build_news_provider(data_dir: str | Path | None = None) -> "HybridNewsProvider":
    load_dotenv()
    return HybridNewsProvider(data_dir)


class HybridNewsProvider:
    """Live-first provider with deterministic fixture fallback."""

    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.mode = os.getenv("NEWS_MODE") or ("live" if _live_enabled() else "fixture")
        self.fixture = FixtureNewsProvider(data_dir)
        self.live = LiveNewsProvider()

    def search(self, query: str, days: int = 7) -> dict[str, Any]:
        if self.mode == "fixture":
            return self.fixture.search(query=query, days=days)
        live_result = self.live.search(query=query, days=days)
        if live_result.get("items") or self.mode == "live":
            return live_result
        fixture_result = self.fixture.search(query=query, days=days)
        fixture_result["fallback_reason"] = live_result.get("error") or {
            "code": "LIVE_EMPTY",
            "message": "Live RSS returned no matching items; fixture fallback used.",
        }
        return fixture_result

    def fetch_article(self, url: str) -> dict[str, Any]:
        if self.mode == "fixture" or url.startswith("fixture://"):
            return self.fixture.fetch_article(url=url)
        live_result = self.live.fetch_article(url=url)
        if "error" not in live_result or self.mode == "live":
            return live_result
        fixture_result = self.fixture.fetch_article(url=url)
        if "error" not in fixture_result:
            fixture_result["fallback_reason"] = live_result["error"]
        return fixture_result


class LiveNewsProvider:
    """RSS + HTML article fetcher using only the Python standard library."""

    def __init__(self, rss_urls: list[str] | None = None) -> None:
        self.rss_urls = rss_urls or _rss_urls_from_env()
        self.timeout = float(os.getenv("HTTP_TIMEOUT_SECONDS", "12"))
        self.retries = int(os.getenv("HTTP_RETRIES", "2"))

    def search(self, query: str, days: int = 7) -> dict[str, Any]:
        terms = _tokenize(query)
        if not terms:
            return {"items": [], "source": "live:rss", "query": query, "days": days}

        min_date = date.today() - timedelta(days=max(days, 1))
        items: list[dict[str, Any]] = []
        errors = []
        for rss_url in self.rss_urls:
            try:
                xml_text = _fetch_text(rss_url, timeout=self.timeout, retries=self.retries)
                parsed_items = _parse_rss(xml_text, rss_url)
            except Exception as exc:  # noqa: BLE001 - returned as structured source error
                errors.append({"url": rss_url, "message": str(exc)})
                continue
            for item in parsed_items:
                published = _parse_date_loose(item.get("published_at")) or date.today()
                if published < min_date:
                    continue
                haystack = " ".join(
                    [item.get("title", ""), item.get("summary", ""), item.get("source", "")]
                ).lower()
                matched = [term for term in terms if term in haystack]
                if not matched:
                    continue
                score = len(set(matched)) / max(len(set(terms)), 1)
                items.append(
                    {
                        "title": item["title"],
                        "url": item["url"],
                        "source": item["source"],
                        "published_at": published.isoformat(),
                        "summary": item["summary"],
                        "matched_terms": sorted(set(matched)),
                        "confidence": round(min(0.98, 0.52 + score * 0.42), 2),
                    }
                )

        items.sort(key=lambda item: (item["confidence"], item["published_at"]), reverse=True)
        result: dict[str, Any] = {
            "items": _dedupe_items(items)[:10],
            "query": query,
            "days": days,
            "source": "live:rss",
            "rss_urls": self.rss_urls,
        }
        if errors:
            result["warnings"] = errors
        return result

    def fetch_article(self, url: str) -> dict[str, Any]:
        try:
            html = _fetch_text(url, timeout=self.timeout, retries=self.retries)
        except Exception as exc:  # noqa: BLE001 - returned as structured source error
            return {
                "error": {
                    "code": "ARTICLE_FETCH_FAILED",
                    "message": str(exc),
                    "details": {"url": url},
                }
            }
        article = _extract_article_text(html)
        if not article["text"]:
            return {
                "error": {
                    "code": "ARTICLE_TEXT_EMPTY",
                    "message": "Article was fetched but no readable text was extracted.",
                    "details": {"url": url},
                }
            }
        return {
            "title": article["title"] or url,
            "url": url,
            "source": "live:html",
            "published_at": article.get("published_at") or date.today().isoformat(),
            "summary": article["text"][:280],
            "text": article["text"],
            "citations": [{"label": "live:html", "url": url}],
        }


class FixtureNewsProvider:
    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.data_dir = _resolve_data_dir(data_dir)
        self.news_path = self.data_dir / "news.jsonl"
        self._items = self._load_items()

    def search(self, query: str, days: int = 7) -> dict[str, Any]:
        terms = _tokenize(query)
        if not terms:
            return {"items": []}

        reference_date = max((_parse_date(item["published_at"]) for item in self._items), default=date.today())
        min_date = reference_date - timedelta(days=max(days, 1))
        scored = []
        for item in self._items:
            published_at = _parse_date(item["published_at"])
            if published_at < min_date:
                continue
            haystack = " ".join(
                [
                    item.get("title", ""),
                    item.get("summary", ""),
                    item.get("text", ""),
                    " ".join(item.get("tags", [])),
                ]
            ).lower()
            matched = [term for term in terms if term in haystack]
            if not matched:
                continue
            score = len(set(matched)) / max(len(set(terms)), 1)
            scored.append((score, item, sorted(set(matched))))

        scored.sort(key=lambda entry: (entry[0], entry[1]["published_at"]), reverse=True)
        return {
            "items": [
                {
                    "title": item["title"],
                    "url": item["url"],
                    "source": item["source"],
                    "published_at": item["published_at"],
                    "summary": item["summary"],
                    "matched_terms": matched,
                    "confidence": round(min(0.99, 0.55 + score * 0.4), 2),
                }
                for score, item, matched in scored[:8]
            ],
            "query": query,
            "days": days,
            "source": "fixture:news.jsonl",
        }

    def fetch_article(self, url: str) -> dict[str, Any]:
        for item in self._items:
            if item["url"] == url:
                return {
                    "title": item["title"],
                    "url": item["url"],
                    "source": item["source"],
                    "published_at": item["published_at"],
                    "summary": item["summary"],
                    "text": item["text"],
                    "citations": [{"label": item["source"], "url": item["url"]}],
                }
        return {
            "error": {
                "code": "ARTICLE_NOT_FOUND",
                "message": "No article matched the provided URL.",
                "details": {"url": url},
            }
        }

    def _load_items(self) -> list[dict[str, Any]]:
        if not self.news_path.exists():
            raise FileNotFoundError(f"news fixture not found: {self.news_path}")
        items: list[dict[str, Any]] = []
        with self.news_path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid JSONL at {self.news_path}:{line_number}") from exc
        return items


def _tokenize(query: str) -> list[str]:
    normalized = query.lower()
    for alias, replacement in ALIASES.items():
        normalized = normalized.replace(alias.lower(), f" {replacement} ")
        normalized = normalized.replace(alias, f" {replacement} ")
    terms = re.findall(r"[a-z0-9_]+(?:\s+ore)?", normalized)
    return [term.strip() for term in terms if len(term.strip()) > 1]


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parse_date_loose(value: str | None) -> date | None:
    if not value:
        return None
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    try:
        return parsedate_to_datetime(value).date()
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def _rss_urls_from_env() -> list[str]:
    raw = os.getenv("NEWS_RSS_URLS", "")
    urls = [part.strip() for part in raw.split(",") if part.strip()]
    return urls or DEFAULT_RSS_URLS


def _live_enabled() -> bool:
    return os.getenv("LIVE_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


def _fetch_text(url: str, timeout: float, retries: int) -> str:
    last_error: Exception | None = None
    for attempt in range(max(retries, 0) + 1):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": os.getenv(
                        "HTTP_USER_AGENT",
                        "Mozilla/5.0 (compatible; mining-daily-mcp-agent/0.1; +https://example.local)",
                    ),
                    "Accept": "text/html,application/rss+xml,application/xml;q=0.9,*/*;q=0.8",
                },
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                content_type = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(content_type, errors="replace")
        except (urllib.error.URLError, TimeoutError, UnicodeDecodeError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(0.4 * (attempt + 1))
    raise RuntimeError(f"HTTP fetch failed for {url}: {last_error}")


def _parse_rss(xml_text: str, source_url: str) -> list[dict[str, Any]]:
    root = ET.fromstring(xml_text)
    channel_items = root.findall(".//item")
    atom_entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")
    parsed: list[dict[str, Any]] = []
    for item in channel_items:
        parsed.append(
            {
                "title": _xml_text(item, "title") or "untitled",
                "url": _xml_text(item, "link") or source_url,
                "source": f"live:rss:{urllib.parse.urlparse(source_url).netloc}",
                "published_at": _xml_text(item, "pubDate") or _xml_text(item, "date"),
                "summary": _strip_html(_xml_text(item, "description") or ""),
            }
        )
    for entry in atom_entries:
        parsed.append(
            {
                "title": _xml_text(entry, "{http://www.w3.org/2005/Atom}title") or "untitled",
                "url": _atom_link(entry) or source_url,
                "source": f"live:rss:{urllib.parse.urlparse(source_url).netloc}",
                "published_at": _xml_text(entry, "{http://www.w3.org/2005/Atom}updated")
                or _xml_text(entry, "{http://www.w3.org/2005/Atom}published"),
                "summary": _strip_html(
                    _xml_text(entry, "{http://www.w3.org/2005/Atom}summary") or ""
                ),
            }
        )
    return parsed


def _xml_text(element: ET.Element, tag: str) -> str | None:
    found = element.find(tag)
    if found is None or found.text is None:
        return None
    return unescape(found.text.strip())


def _atom_link(entry: ET.Element) -> str | None:
    for link in entry.findall("{http://www.w3.org/2005/Atom}link"):
        href = link.attrib.get("href")
        if href:
            return href
    return None


def _strip_html(value: str) -> str:
    parser = _ReadableHTMLParser()
    parser.feed(value)
    text = " ".join(parser.text_parts)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _extract_article_text(html: str) -> dict[str, str]:
    parser = _ReadableHTMLParser()
    parser.feed(html)
    title = parser.title.strip()
    text = re.sub(r"\s+", " ", " ".join(parser.text_parts)).strip()
    return {"title": unescape(title), "text": unescape(text)}


class _ReadableHTMLParser(HTMLParser):
    SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "footer", "header"}
    TEXT_TAGS = {"p", "li", "h1", "h2", "h3", "td", "th", "article", "section"}

    def __init__(self) -> None:
        super().__init__()
        self.skip_depth = 0
        self.capture_title = False
        self.title = ""
        self.text_parts: list[str] = []
        self._active_text_tag = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP_TAGS:
            self.skip_depth += 1
        if tag == "title":
            self.capture_title = True
        if tag in self.TEXT_TAGS:
            self._active_text_tag = True

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        if tag == "title":
            self.capture_title = False
        if tag in self.TEXT_TAGS:
            self._active_text_tag = False

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        cleaned = re.sub(r"\s+", " ", data).strip()
        if not cleaned:
            return
        if self.capture_title:
            self.title += f" {cleaned}"
        elif self._active_text_tag or len(cleaned) > 80:
            self.text_parts.append(cleaned)


def _dedupe_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped = []
    for item in items:
        key = item["url"].split("?")[0].rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


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
