from servers.mineral_pdf_mcp.extractor import ResourceExtractor, extract_resources_from_text


def test_fixture_extracts_indicated_and_inferred() -> None:
    result = ResourceExtractor().extract_resources("fixture://reports/pilbara-ni-43-101")

    categories = {item["category"] for item in result["resources"]}
    assert categories == {"Indicated", "Inferred"}
    assert result["needs_human_review"] is False


def test_text_extractor_marks_incomplete_result_for_review() -> None:
    result = extract_resources_from_text("Indicated 10 Mt 1.0 % Li2O 0.1 Mt Li2O", "memory://sample")

    assert result["needs_human_review"] is True
    assert result["resources"][0]["category"] == "Indicated"

