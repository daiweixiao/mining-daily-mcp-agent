from agent.mcp_client import LocalToolClient
from agent.orchestrator import MiningDailyAgent


def test_agent_generates_markdown_report() -> None:
    report = MiningDailyAgent(LocalToolClient()).generate_report("给我生成一份关于Pilbara锂矿的今日简报")

    assert report.startswith("# Pilbara Lithium 矿权日报")
    assert "## 1. 新闻摘要" in report
    assert "## 2. 储量数据" in report
    assert "Indicated" in report
    assert "Inferred" in report
    assert "## 3. 价格走势" in report
    assert "## 5. 引用源" in report


def test_agent_uses_rule_renderer_when_llm_disabled(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "false")

    report = MiningDailyAgent(LocalToolClient()).generate_report("给我生成一份关于Pilbara锂矿的今日简报")

    assert "LLM 增强失败" not in report
    assert "数据来源" in report
