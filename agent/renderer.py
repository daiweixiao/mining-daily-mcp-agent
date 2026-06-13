from __future__ import annotations

from datetime import date
from typing import Any

from agent.schemas import ReportRequest


def render_report(
    request: ReportRequest,
    news: dict[str, Any],
    articles: list[dict[str, Any]],
    resources: dict[str, Any],
    price: dict[str, Any],
    trend: dict[str, Any],
) -> str:
    citations = _collect_citations(articles, resources, price)
    lines: list[str] = []
    lines.append(f"# {request.project} {request.commodity.title()} 矿权日报")
    lines.append("")
    lines.append(f"生成日期：{date.today().isoformat()}")
    lines.append("")
    lines.append("## 1. 新闻摘要")
    lines.append("")
    if articles:
        for idx, article in enumerate(articles, start=1):
            summary = article.get("summary") or article.get("text", "")[:180]
            lines.append(f"- {summary} [{idx}]")
    else:
        lines.append("- 未检索到高置信度新闻，建议人工补充最新公告。")
    lines.append("")

    lines.append("## 2. 储量数据")
    lines.append("")
    warnings = resources.get("warnings") or []
    if resources.get("needs_human_review"):
        lines.append("储量抽取结果置信度不足，已标记为待人工审核。")
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("| 分类 | 矿石量 | 品位 | 金属量 | 证据 |")
        lines.append("| --- | ---: | ---: | ---: | --- |")
        for item in resources.get("resources", []):
            ore = _format_number(item.get("ore_tonnage_mt"))
            grade = _format_number(item.get("grade"))
            metal = _format_number(item.get("metal_content"))
            lines.append(
                "| {category} | {ore} Mt | {grade} {grade_unit} | "
                "{metal} {metal_unit} | {evidence} |".format(
                    category=item.get("category", "Unknown"),
                    ore=ore,
                    grade=grade,
                    grade_unit=item.get("grade_unit", ""),
                    metal=metal,
                    metal_unit=item.get("metal_unit", ""),
                    evidence=item.get("evidence", ""),
                )
            )
    lines.append("")

    lines.append("## 3. 价格走势")
    lines.append("")
    if "error" in trend:
        lines.append(f"- 价格趋势不可用：{trend['error'].get('message', 'unknown error')}")
    else:
        direction = {
            "up": "上行",
            "down": "下行",
            "flat": "基本持平",
        }.get(trend.get("direction"), trend.get("direction", "未知"))
        lines.append(
            "- {commodity} 近 {days} 天从 {start} {currency}/{unit} "
            "变动至 {end} {currency}/{unit}，变化 {change_pct}%，趋势为{direction}。".format(
                commodity=trend.get("commodity", request.commodity),
                days=trend.get("days", request.price_days),
                start=_format_number(trend.get("start_price")),
                end=_format_number(trend.get("end_price")),
                currency=price.get("currency", trend.get("currency", "USD")),
                unit=price.get("unit", trend.get("unit", "t")),
                change_pct=_format_number(trend.get("change_pct")),
                direction=direction,
            )
        )
        if "price" in price:
            lines.append(
                f"- 最新可用价格日期：{price.get('date')}，价格："
                f"{_format_number(price.get('price'))} {price.get('currency')}/{price.get('unit')}。"
            )
    lines.append("")

    lines.append("## 4. 风险提示")
    lines.append("")
    for risk in _build_risks(news, resources, trend):
        lines.append(f"- {risk}")
    lines.append("")

    lines.append("## 5. 引用源")
    lines.append("")
    if citations:
        for idx, citation in enumerate(citations, start=1):
            lines.append(f"[{idx}] {citation['title']} - {citation['url']}")
    else:
        lines.append("暂无引用源。")
    lines.append("")
    lines.append(f"> 数据来源：{_source_summary(news, resources, price, trend)}")
    return "\n".join(lines)


def _build_risks(
    news: dict[str, Any], resources: dict[str, Any], trend: dict[str, Any]
) -> list[str]:
    risks = []
    if trend.get("direction") == "down":
        risks.append("价格端：近 30 天价格走弱，项目现金流和估值假设需做敏感性测试。")
    elif trend.get("direction") == "up":
        risks.append("价格端：价格上行改善收入预期，但也可能推高扩产和长协谈判波动。")
    else:
        risks.append("价格端：价格趋势不明显，需持续跟踪库存、下游需求和现货成交。")

    if resources.get("needs_human_review"):
        risks.append("资源端：储量/资源量抽取置信度不足，投资判断前需要人工复核技术报告。")
    else:
        risks.append("资源端：资源量数据来自技术报告摘要，仍需结合最新公告、采矿回收率和边界品位复核。")

    if news.get("items"):
        risks.append("政策与舆情端：新闻变化可能影响审批、出口、融资和社区关系，应保留来源追溯。")
    else:
        risks.append("信息端：当前新闻覆盖不足，正式日报应补充公司公告和监管披露。")
    return risks


def _collect_citations(
    articles: list[dict[str, Any]], resources: dict[str, Any], price: dict[str, Any]
) -> list[dict[str, str]]:
    seen: set[str] = set()
    citations: list[dict[str, str]] = []

    def add(title: str | None, url: str | None) -> None:
        if not url or url in seen:
            return
        seen.add(url)
        citations.append({"title": title or "source", "url": url})

    for article in articles:
        add(article.get("title"), article.get("url"))
    add(resources.get("project") or "resource report", resources.get("source_url") or resources.get("document_url"))
    add(f"{price.get('commodity', 'commodity')} price", price.get("source_url"))
    return citations


def _format_number(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, (int, float)):
        if abs(value) >= 100:
            return f"{value:,.0f}"
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    return str(value)


def _source_summary(
    news: dict[str, Any], resources: dict[str, Any], price: dict[str, Any], trend: dict[str, Any]
) -> str:
    parts = [
        f"news={news.get('source', 'unknown')}",
        f"resources={resources.get('source_url') or resources.get('document_url') or 'unknown'}",
        f"price={price.get('source', trend.get('source', 'unknown'))}",
    ]
    fallback_notes = []
    for payload in [news, price, trend]:
        reason = payload.get("fallback_reason")
        if isinstance(reason, dict):
            fallback_notes.append(reason.get("code", "fallback"))
    if fallback_notes:
        parts.append("fallback=" + ",".join(sorted(set(fallback_notes))))
    return "; ".join(parts)
