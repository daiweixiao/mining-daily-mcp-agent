from pathlib import Path

from servers.mining_news_mcp.providers import FixtureNewsProvider, LiveNewsProvider


def test_search_returns_pilbara_lithium_news() -> None:
    result = FixtureNewsProvider().search("Pilbara lithium", days=7)

    assert result["items"]
    assert result["items"][0]["title"]
    assert result["items"][0]["url"]
    assert result["items"][0]["confidence"] >= 0.55


def test_fetch_article_returns_text() -> None:
    provider = FixtureNewsProvider()
    item = provider.search("Pilbara lithium", days=7)["items"][0]
    article = provider.fetch_article(item["url"])

    assert "error" not in article
    assert article["text"]
    assert article["citations"][0]["url"] == item["url"]


def test_fetch_missing_article_returns_structured_error() -> None:
    result = FixtureNewsProvider().fetch_article("https://missing.example/article")

    assert result["error"]["code"] == "ARTICLE_NOT_FOUND"


def test_live_news_provider_reads_file_rss_and_article(tmp_path: Path) -> None:
    article_path = tmp_path / "article.html"
    article_path.write_text(
        """
        <html><head><title>Pilbara lithium update</title></head>
        <body><article><p>Pilbara lithium export policy and spodumene pricing are in focus.</p></article></body></html>
        """,
        encoding="utf-8",
    )
    rss_path = tmp_path / "feed.xml"
    rss_path.write_text(
        f"""
        <rss version="2.0"><channel><item>
          <title>Pilbara lithium export policy update</title>
          <link>{article_path.as_uri()}</link>
          <pubDate>Fri, 12 Jun 2026 08:00:00 GMT</pubDate>
          <description>Pilbara lithium policy and prices.</description>
        </item></channel></rss>
        """,
        encoding="utf-8",
    )
    provider = LiveNewsProvider([rss_path.as_uri()])

    search = provider.search("Pilbara lithium", days=7)
    article = provider.fetch_article(search["items"][0]["url"])

    assert search["items"][0]["source"].startswith("live:rss")
    assert article["source"] == "live:html"
    assert "spodumene" in article["text"]
