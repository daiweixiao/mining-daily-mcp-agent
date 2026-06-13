# Data Source Notes

This project is live-first capable and fixture-safe.

## Modes

Default mode is deterministic fixture mode:

```bash
python -m agent.cli --transport mcp "给我生成一份关于Pilbara锂矿的今日简报"
```

Live-capable mode:

```bash
LIVE_MODE=true NEWS_MODE=auto python -m agent.cli --transport mcp "给我生成一份关于Pilbara锂矿的今日简报"
```

`auto` mode tries live sources first and falls back to fixtures when live data is unavailable.

## .env

The project automatically loads `.env` from the repository root. You can also point to another file:

```bash
ENV_FILE=C:/path/to/mining-agent.env python -m agent.cli
```

Do not commit real `.env` files. Commit `.env.example` only.

Optional LLM settings:

```text
OPENAI_BASE_URL=https://wzw.pp.ua/v1
OPENAI_MODEL=deepseek-ai/deepseek-v4-flash
OPENAI_API_KEY=replace-with-your-api-key
LLM_ENABLED=true
```

When enabled, the Agent uses the model only after MCP tools return structured evidence. If the model call fails, the report falls back to the deterministic renderer.

## News

Tools:

- `search(query, days)`
- `fetch_article(url)`

Live configuration:

```text
LIVE_MODE=true
NEWS_MODE=auto|live|fixture
NEWS_RSS_URLS=https://www.mining.com/feed/,https://your-spglobal-rss-url.example/feed.xml
HTTP_TIMEOUT_SECONDS=12
HTTP_RETRIES=2
```

Behavior:

- Reads RSS feeds.
- Filters items by query and day window.
- Fetches article HTML.
- Extracts readable text with a standard-library HTML parser.
- Deduplicates by canonicalized URL.
- Returns `source=live:rss` or `source=live:html`.

## PDF / NI 43-101 Resource Extraction

Tool:

- `extract_resources(pdf_url)`

Supported inputs:

- Fixture URL: `fixture://reports/pilbara-ni-43-101`
- Local `.txt` / `.md`
- Local `.pdf` when PyMuPDF is installed
- Remote `http(s)` PDF/text/HTML URL

Agent-level configuration:

```text
RESOURCE_PDF_URL=https://example.com/path/to/ni-43-101.pdf
```

Install live PDF support:

```bash
pip install -e ".[live]"
```

If PDF parsing fails or PyMuPDF is unavailable, the tool returns `needs_human_review=true` with a structured warning.

## Prices

Tools:

- `get_price(commodity, date)`
- `get_trend(commodity, days)`

Live/manual configuration:

```text
PRICE_MODE=auto|live|fixture
PRICE_CSV_PATH=/path/to/prices.csv
PRICE_API_URL=https://price-api.example.com/prices?commodity={commodity}&date={date}&days={days}
```

Expected CSV schema:

```csv
date,commodity,price,currency,unit,source,source_url
2026-06-12,lithium,14300,USD,t,my-provider,https://example.com/source
```

Expected JSON API response can be a single object:

```json
{
  "date": "2026-06-12",
  "commodity": "lithium",
  "price": 14300,
  "currency": "USD",
  "unit": "t",
  "source_url": "https://example.com/source"
}
```

Or a list / `items` / `observations` array with the same fields.

Because LME, SHFE, and Mysteel data often require authorization or login, the project does not hard-code brittle scraping for those sources. It accepts authorized API/CSV inputs and falls back to fixture data when unavailable.

## Health Check

Check active sources without generating a report:

```bash
python -m agent.healthcheck --query "Pilbara lithium" --commodity lithium
```

Live smoke check:

```bash
LIVE_MODE=true NEWS_MODE=auto NEWS_RSS_URLS="https://your-rss-feed.example/feed.xml" python -m agent.healthcheck
```

The output includes source labels, warnings, and fallback reasons.
