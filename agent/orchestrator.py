from __future__ import annotations

import re
import os
from typing import Any

from agent.llm import enhance_report
from agent.renderer import render_report
from agent.schemas import ReportRequest
from project_env import load_dotenv


PROJECT_RESOURCE_URLS = {
    "pilbara": "fixture://reports/pilbara-ni-43-101",
}

COMMODITY_ALIASES = {
    "锂": "lithium",
    "锂矿": "lithium",
    "lithium": "lithium",
    "铜": "copper",
    "copper": "copper",
    "锌": "zinc",
    "zinc": "zinc",
    "镍": "nickel",
    "nickel": "nickel",
    "铁矿石": "iron_ore",
    "iron ore": "iron_ore",
}


class MiningDailyAgent:
    def __init__(self, tool_client: Any) -> None:
        self.tool_client = tool_client

    def generate_report(self, prompt: str) -> str:
        load_dotenv()
        request = parse_request(prompt)
        news_query = f"{request.project} {request.commodity}"

        news = self.tool_client.search_news(news_query, request.news_days)
        articles = []
        for item in news.get("items", [])[:3]:
            article = self.tool_client.fetch_article(item["url"])
            if "error" not in article:
                articles.append(article)

        resource_url = os.getenv("RESOURCE_PDF_URL") or PROJECT_RESOURCE_URLS.get(
            request.project.lower(), "fixture://reports/pilbara-ni-43-101"
        )
        resources = self.tool_client.extract_resources(resource_url)
        price = self.tool_client.get_price(request.commodity)
        trend = self.tool_client.get_trend(request.commodity, request.price_days)

        base_report = render_report(
            request=request,
            news=news,
            articles=articles,
            resources=resources,
            price=price,
            trend=trend,
        )
        return enhance_report(
            base_report=base_report,
            evidence={
                "request": request.__dict__,
                "news": news,
                "articles": articles,
                "resources": resources,
                "price": price,
                "trend": trend,
            },
        )


def parse_request(prompt: str) -> ReportRequest:
    prompt_lower = prompt.lower()
    project = "Pilbara"
    project_match = re.search(r"(pilbara|pilgangoora|newmont|barrick)", prompt_lower)
    if project_match:
        project = project_match.group(1).title()

    commodity = "lithium"
    for alias, normalized in COMMODITY_ALIASES.items():
        if alias in prompt_lower or alias in prompt:
            commodity = normalized
            break

    news_days = 7
    days_match = re.search(r"近\s*(\d+)\s*天|(\d+)\s*days?", prompt_lower)
    if days_match:
        news_days = int(days_match.group(1) or days_match.group(2))

    return ReportRequest(
        prompt=prompt,
        project=project,
        commodity=commodity,
        news_days=news_days,
        price_days=30,
    )
