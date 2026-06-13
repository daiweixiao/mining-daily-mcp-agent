from agent import llm


def test_llm_enhancement_can_be_enabled_without_network(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(llm, "_chat_completion", lambda messages: "## Enhanced\n\nOK")

    result = llm.enhance_report("## Base\n\nOriginal", {"source": "test"})

    assert result.startswith("## Enhanced")


def test_llm_enhancement_falls_back_on_error(monkeypatch) -> None:
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fail(_messages):
        raise RuntimeError("boom")

    monkeypatch.setattr(llm, "_chat_completion", fail)

    result = llm.enhance_report("## Base\n\nOriginal", {"source": "test"})

    assert "## Base" in result
    assert "LLM 增强失败" in result

