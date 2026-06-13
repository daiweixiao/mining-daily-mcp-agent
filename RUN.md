# RUN

本项目用于题 #2：MCP 矿权日报 Agent。默认 fixture-first，可离线演示。

## 1. Docker Compose 一键运行

```bash
docker compose up --build
```

该命令默认使用 MCP stdio 路径：Agent 会分别启动并调用 `mining-news-mcp`、`mineral-pdf-mcp`、`lme-price-mcp`。

预期输出是一份 Markdown 简报，包含：

- 新闻摘要
- Indicated / Inferred 储量数据
- 锂价 30 天趋势
- 风险提示
- 引用源链接

## 2. 本地 Python 运行

建议 Python 3.11+。

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
python -m agent.cli "给我生成一份关于Pilbara锂矿的今日简报"
```

可选 `.env` 配置：

```bash
copy .env.example .env
```

然后编辑 `.env`：

```text
OPENAI_BASE_URL=https://wzw.pp.ua/v1
OPENAI_MODEL=deepseek-ai/deepseek-v4-flash
OPENAI_API_KEY=replace-with-your-api-key
LLM_ENABLED=true
```

`.env` 会被项目自动读取，且已在 `.gitignore` 中忽略。

如果只想使用 fixture provider，不需要启动 MCP server：

```bash
python -m agent.cli --transport local "给我生成一份关于Pilbara锂矿的今日简报"
```

如果要通过 MCP stdio server 调用：

```bash
python -m agent.cli --transport mcp "给我生成一份关于Pilbara锂矿的今日简报"
```

生成可查看的 Markdown 文件：

```bash
python -m agent.cli --transport mcp --output examples/pilbara_daily_report.md "给我生成一份关于Pilbara锂矿的今日简报"
```

### Report output

Every CLI run writes a Markdown copy to:

```text
reports/mining_daily_<timestamp>.md
```

Use `--output path/to/report.md` to write to a specific path instead. The generated `reports/*.md` files are ignored by Git. On Windows PowerShell, prefer `python -X utf8 -B -m agent.cli ...` when LLM output contains Unicode symbols such as `Li2O` subscripts.

## 3. Claude Code / Claude Desktop / Cursor 接入

**Claude Code**：仓库根目录已包含 `.mcp.json`，在项目目录启动 Claude Code 即自动加载 3 个 MCP server：

```bash
cd mining-daily-mcp-agent
claude
# 进入后输入 /mcp 确认 server 已加载
```

**Claude Desktop / Cursor**：使用仓库根目录的 `mcp-config.json`。

如客户端启动目录不是仓库根目录，请把每个 server 的 `DATA_DIR` 改成你的 fixture 数据目录，或在客户端配置里设置工作目录为仓库根目录。

配置内容：

```json
{
  "mcpServers": {
    "mining-news-mcp": {
      "command": "python",
      "args": ["-m", "servers.mining_news_mcp.server"],
      "env": {
        "DATA_DIR": "data/fixtures"
      }
    },
    "mineral-pdf-mcp": {
      "command": "python",
      "args": ["-m", "servers.mineral_pdf_mcp.server"],
      "env": {
        "DATA_DIR": "data/fixtures"
      }
    },
    "lme-price-mcp": {
      "command": "python",
      "args": ["-m", "servers.lme_price_mcp.server"],
      "env": {
        "DATA_DIR": "data/fixtures"
      }
    }
  }
}
```

## 4. 验证

```bash
python -m pytest
python -m agent.cli "给我生成一份关于Pilbara锂矿的今日简报"
```

## 5. 当前实现边界

- 默认使用 fixture 数据，保证评审环境稳定复现。
- live 模式支持新闻 RSS/HTML 抓取、远程 PDF 下载、价格 API/CSV 接入。
- PDF 抽取支持 fixture、本地文本、本地 PDF、远程 PDF；PDF 解析需要安装 PyMuPDF。
- 数据证据不足时返回 `needs_human_review=true`，不会硬编结果。

## 6. 真实使用模式

安装 live PDF 解析能力：

```bash
pip install -e ".[dev,live]"
```

新闻 live-first：

```bash
LIVE_MODE=true NEWS_MODE=auto NEWS_RSS_URLS="https://www.mining.com/feed/" python -m agent.cli --transport mcp "给我生成一份关于Pilbara锂矿的今日简报"
```

价格 live/manual：

```bash
PRICE_MODE=auto PRICE_CSV_PATH=/path/to/prices.csv python -m agent.cli --transport mcp "给我生成一份关于Pilbara锂矿的今日简报"
```

真实 PDF：

```bash
RESOURCE_PDF_URL="https://example.com/path/to/ni-43-101.pdf" python -m agent.cli --transport mcp "给我生成一份关于Pilbara锂矿的今日简报"
```

通用价格 API：

```bash
PRICE_MODE=auto PRICE_API_URL="https://price-api.example.com/prices?commodity={commodity}&date={date}&days={days}" python -m agent.cli --transport mcp "给我生成一份关于Pilbara锂矿的今日简报"
```

Docker live profile：

```bash
docker compose --profile live up --build mining-daily-agent-live
```

详细数据源说明见 `DATA_SOURCE_NOTES.md`。
Claude Desktop / Cursor 的 live 配置示例见 `mcp-config.live.example.json`。

数据源健康检查：

```bash
python -m agent.healthcheck
```
