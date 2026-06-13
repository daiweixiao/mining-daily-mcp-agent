from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ReportRequest:
    prompt: str
    project: str
    commodity: str
    news_days: int = 7
    price_days: int = 30


ToolPayload = dict[str, Any]

