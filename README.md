# MCP Mining Daily Agent

题 #2 实现：基于 MCP (Model Context Protocol) 的“矿权日报 Agent”。

项目包含 3 个 MCP server 和 1 个 client 端 Agent：

- `mining-news-mcp`：新闻搜索与文章获取，工具为 `search(query, days)`、`fetch_article(url)`。
- `mineral-pdf-mcp`：NI 43-101 储量抽取，工具为 `extract_resources(pdf_url)`。
- `lme-price-mcp`：价格点查与趋势，工具为 `get_price(commodity, date)`、`get_trend(commodity, days)`。
- `agent`：编排以上工具，生成 Markdown 矿权日报。

默认使用 fixture 数据，保证无网络、无 API key 环境也可以 5 分钟内跑通；真实 RSS、PDF、价格 API 可通过 provider 扩展接入。
现在也支持 live-first 模式：新闻 RSS/正文抓取、远程 PDF 下载抽取、价格 API/CSV 接入，并保留 fixture fallback。

## Quick Start

安装依赖：

```bash
pip install -e ".[dev]"
```

可选：复制 `.env.example` 为 `.env`，在本地填写模型和 live 数据源配置。`.env` 已被 `.gitignore` 忽略，不要提交真实 key。

```bash
copy .env.example .env
```

生成默认简报：

```bash
python -m agent.cli "给我生成一份关于Pilbara锂矿的今日简报"
```

或使用 MCP stdio client 调用 3 个 server：

```bash
python -m agent.cli --transport mcp "给我生成一份关于Pilbara锂矿的今日简报"
```

写入 Markdown 文件：

```bash
python -m agent.cli --transport mcp --output examples/pilbara_daily_report.md "给我生成一份关于Pilbara锂矿的今日简报"
```

## Report Output

- Every CLI run writes a Markdown copy to `reports/mining_daily_<timestamp>.md`.
- Use `--output path/to/report.md` to write to a specific path instead.
- `reports/*.md` is ignored by Git so generated daily reports are not committed accidentally.
- On Windows PowerShell, use `python -X utf8 -B -m agent.cli ...` if the report contains symbols such as `Li2O` with Unicode subscripts.

## Docker

```bash
docker compose up --build
```

Docker 默认使用 `--transport mcp`，会通过 MCP stdio 启动并调用 3 个 server。

Live 模式 Docker：

```bash
docker compose --profile live up --build mining-daily-agent-live
```

## Tests

```bash
python -m pytest
```

## MCP Tools

### mining-news-mcp

```bash
python -m servers.mining_news_mcp.server
```

Tools:

- `search(query: str, days: int)`
- `fetch_article(url: str)`

### mineral-pdf-mcp

```bash
python -m servers.mineral_pdf_mcp.server
```

Tool:

- `extract_resources(pdf_url: str)`

### lme-price-mcp

```bash
python -m servers.lme_price_mcp.server
```

Tools:

- `get_price(commodity: str, date: str | None)`
- `get_trend(commodity: str, days: int)`

## Data Contract

所有工具返回结构化 JSON。关键字段包括：

- 新闻：`title`、`url`、`source`、`published_at`、`summary`、`confidence`。
- 储量：`category`、`ore_tonnage_mt`、`grade`、`grade_unit`、`metal_content`、`metal_unit`、`evidence`、`confidence`。
- 价格：`commodity`、`date`、`price`、`currency`、`unit`、`source_url`。

若证据不足，工具返回结构化错误或 `needs_human_review=true`，不编造结论。

## Implementation Notes

- `local` transport：直接调用 fixture provider，适合单元测试和无 MCP SDK 场景。
- `mcp` transport：通过 MCP stdio client 启动并调用 3 个 MCP server，适合正式演示。
- fixture 数据放在 `data/fixtures/`，真实 RSS、PDF 和价格 API 可在 provider 层替换。

## Live Mode

### Optional LLM Enhancement

题 #2 不强制依赖 LLM。项目默认不用模型，保证离线可复现。若要启用你提供的 OpenAI-compatible 模型，在 `.env` 中设置：

```text
OPENAI_BASE_URL=https://wzw.pp.ua/v1
OPENAI_MODEL=deepseek-ai/deepseek-v4-flash
OPENAI_API_KEY=replace-with-your-api-key
LLM_ENABLED=true
```

启用后，Agent 会先用 MCP 工具生成证据版日报，再调用模型润色中文摘要和风险提示；模型失败会自动回退到规则版。

新闻 RSS：

```bash
LIVE_MODE=true NEWS_MODE=auto NEWS_RSS_URLS="https://www.mining.com/feed/" \
python -m agent.cli --transport mcp "给我生成一份关于Pilbara锂矿的今日简报"
```

PDF 抽取：

```bash
pip install -e ".[live]"
RESOURCE_PDF_URL="https://example.com/path/to/ni-43-101.pdf" \
python -m agent.cli --transport mcp "给我生成一份关于Pilbara锂矿的今日简报"
```

价格源：

```bash
PRICE_MODE=auto PRICE_CSV_PATH=/path/to/prices.csv \
python -m agent.cli --transport mcp "给我生成一份关于Pilbara锂矿的今日简报"
```

更多数据源配置见 `DATA_SOURCE_NOTES.md`。

检查当前数据源：

```bash
python -m agent.healthcheck
```

Claude Desktop / Cursor 的 live 配置示例见 `mcp-config.live.example.json`。
