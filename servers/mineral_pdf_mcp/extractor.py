from __future__ import annotations

import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


class ResourceExtractor:
    def __init__(self, data_dir: str | Path | None = None) -> None:
        self.data_dir = _resolve_data_dir(data_dir)
        self.resources_path = self.data_dir / "resources.json"

    def extract_resources(self, pdf_url: str) -> dict[str, Any]:
        fixtures = self._load_fixtures()
        if pdf_url in fixtures:
            return fixtures[pdf_url]

        text_result = self._load_text(pdf_url)
        if "error" in text_result:
            return self._needs_review(pdf_url, text_result["error"]["message"])
        extracted = extract_resources_from_text(text_result["text"], pdf_url)
        if not extracted.get("resources"):
            return self._needs_review(pdf_url, "No reliable Indicated/Inferred table found.")
        return extracted

    def _load_fixtures(self) -> dict[str, Any]:
        if not self.resources_path.exists():
            raise FileNotFoundError(f"resource fixture not found: {self.resources_path}")
        with self.resources_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data.get("documents", {})

    def _load_text(self, pdf_url: str) -> dict[str, Any]:
        if pdf_url.startswith(("http://", "https://")):
            return _load_remote_document_text(pdf_url)
        path = Path(pdf_url)
        if path.exists() and path.suffix.lower() in {".txt", ".md"}:
            return {"text": path.read_text(encoding="utf-8")}
        if path.exists() and path.suffix.lower() == ".pdf":
            return _extract_pdf_text_from_path(path)
        return {
            "error": {
                "code": "DOCUMENT_NOT_FOUND",
                "message": "Document URL is not in fixtures and is not a local text/PDF path.",
            }
        }

    def _needs_review(self, pdf_url: str, message: str) -> dict[str, Any]:
        return {
            "project": "unknown",
            "document_url": pdf_url,
            "source_url": pdf_url,
            "resources": [],
            "needs_human_review": True,
            "warnings": [message],
        }


def extract_resources_from_text(text: str, document_url: str) -> dict[str, Any]:
    resources = []
    pattern = re.compile(
        r"(?P<category>Measured\s+and\s+Indicated|Measured\s*&\s*Indicated|Indicated|Inferred)"
        r"[\s:;-]+"
        r"(?P<ore>[\d,.]+)\s*(?P<ore_unit>Mt|million\s+tonnes|kt|tonnes)\s+"
        r"(?P<grade>[\d,.]+)\s*(?P<grade_unit>%\s*[A-Za-z0-9]+|g/t\s*[A-Za-z]+)\s+"
        r"(?P<metal>[\d,.]+)\s*(?P<metal_unit>Mt\s*[A-Za-z0-9]+|kt\s*[A-Za-z0-9]+|koz|Moz|oz|t)",
        re.IGNORECASE,
    )
    for match in pattern.finditer(text):
        category = re.sub(r"\s+", " ", match.group("category")).strip().title()
        if category in {"Measured And Indicated", "Measured & Indicated"}:
            category = "Indicated"
        resources.append(
            {
                "category": category,
                "ore_tonnage_mt": _ore_to_mt(_to_float(match.group("ore")), match.group("ore_unit")),
                "grade": _to_float(match.group("grade")),
                "grade_unit": " ".join(match.group("grade_unit").split()),
                "metal_content": _to_float(match.group("metal")),
                "metal_unit": " ".join(match.group("metal_unit").split()),
                "evidence": _evidence_snippet(text, match.start(), match.end()),
                "confidence": 0.68,
            }
        )
    return {
        "project": "extracted document",
        "document_url": document_url,
        "source_url": document_url,
        "resources": resources,
        "needs_human_review": len(resources) < 2,
        "warnings": [] if len(resources) >= 2 else ["Expected both Indicated and Inferred rows."],
    }


def _to_float(value: str) -> float:
    return float(value.replace(",", ""))


def _ore_to_mt(value: float, unit: str) -> float:
    normalized = unit.strip().lower()
    if normalized in {"mt", "million tonnes"}:
        return value
    if normalized == "kt":
        return value / 1000
    if normalized == "tonnes":
        return value / 1_000_000
    return value


def _load_remote_document_text(url: str) -> dict[str, Any]:
    try:
        payload, content_type = _fetch_binary(url)
    except Exception as exc:  # noqa: BLE001 - converted to structured error
        return {
            "error": {
                "code": "DOCUMENT_FETCH_FAILED",
                "message": str(exc),
                "details": {"url": url},
            }
        }
    is_pdf = "pdf" in content_type.lower() or url.lower().split("?")[0].endswith(".pdf")
    if is_pdf:
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as handle:
            handle.write(payload)
            temp_path = Path(handle.name)
        try:
            return _extract_pdf_text_from_path(temp_path)
        finally:
            try:
                temp_path.unlink()
            except OSError:
                pass
    charset = "utf-8"
    if "charset=" in content_type:
        charset = content_type.split("charset=", 1)[1].split(";", 1)[0].strip()
    return {"text": payload.decode(charset or "utf-8", errors="replace")}


def _extract_pdf_text_from_path(path: Path) -> dict[str, Any]:
    try:
        import fitz  # type: ignore
    except ImportError:
        return {
            "error": {
                "code": "PDF_READER_UNAVAILABLE",
                "message": "PyMuPDF is not installed. Install live extras with `pip install -e .[live]`.",
            }
        }
    try:
        with fitz.open(path) as document:
            return {"text": "\n".join(page.get_text("text") for page in document)}
    except Exception as exc:  # noqa: BLE001
        return {
            "error": {
                "code": "PDF_TEXT_EXTRACTION_FAILED",
                "message": str(exc),
                "details": {"path": str(path)},
            }
        }


def _fetch_binary(url: str) -> tuple[bytes, str]:
    timeout = float(os.getenv("HTTP_TIMEOUT_SECONDS", "20"))
    retries = int(os.getenv("HTTP_RETRIES", "2"))
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
                    "Accept": "application/pdf,text/plain,text/html,*/*;q=0.8",
                },
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read(), response.headers.get("Content-Type", "")
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"document fetch failed for {url}: {last_error}")


def _evidence_snippet(text: str, start: int, end: int) -> str:
    left = max(0, start - 80)
    right = min(len(text), end + 80)
    snippet = re.sub(r"\s+", " ", text[left:right]).strip()
    return snippet[:260]


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
