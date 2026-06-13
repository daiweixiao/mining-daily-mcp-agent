# 题 #2：MCP 矿权日报 Agent 详细实施计划

## 1. 目标结论

本项目选择实现题 #2：按 MCP (Model Context Protocol) 协议搭建一个“矿权日报 Agent”，包含至少 3 个 MCP server 和 1 个 client 端 Agent 编排程序。

最终交付目标：

1. 实现 3 个可独立运行的 MCP server：
   - `mining-news-mcp`：矿业新闻聚合。
   - `mineral-pdf-mcp`：NI 43-101 PDF 储量抽取。
   - `lme-price-mcp`：金属/矿产品价格行情。
2. 实现 1 个 Agent client：
   - 输入：“给我生成一份关于 Pilbara 锂矿的今日简报”
   - 输出：Markdown 简报，包含新闻摘要、储量数据、价格走势、风险提示和引用源链接。
3. 提供 `mcp-config.json`：
   - 可直接接入 Claude Desktop / Cursor 验证。
4. 提供 `RUN.md`：
   - 评审人员可在 5 分钟内跑起来。
   - 包含一条 `docker compose` 命令。
5. 满足工程化规范：
   - 清晰目录结构。
   - 可测试。
   - 可复现。
   - fixture-first，确保无外网/无 API key 环境也能演示。
   - 保留真实数据源扩展接口。

## 2. 选题理由

相比题 #1 和题 #3，题 #2 更适合 24 小时工程化交付：

| 题目 | 优势 | 主要风险 | 24h 可控性 |
| --- | --- | --- | --- |
| 题 #1 三源聚合 RAG | 数据工程完整，展示 RAG 能力 | 每源 30 天 200 条、价格源登录/频控、数据真实性难控 | 中低 |
| 题 #2 MCP 矿权日报 Agent | 边界清楚，MCP + Agent 可演示性强 | 需要 MCP server/client 真正跑通 | 高 |
| 题 #3 对抗审核 PDF 抽取 | 技术亮点强，适合展示可靠性 | 依赖真实 PDF、ground truth 和模型 key | 中 |

本项目优先选择题 #2，因为它可以在短时间内交付一个可运行、可验证、结构清楚的 Agent 系统。

## 3. 交付物清单

计划最终仓库结构如下：

```text
.
├── agent/
│   ├── __init__.py
│   ├── cli.py
│   ├── orchestrator.py
│   ├── mcp_client.py
│   ├── renderer.py
│   └── schemas.py
├── servers/
│   ├── mining_news_mcp/
│   │   ├── __init__.py
│   │   ├── server.py
│   │   ├── providers.py
│   │   └── schemas.py
│   ├── mineral_pdf_mcp/
│   │   ├── __init__.py
│   │   ├── server.py
│   │   ├── extractor.py
│   │   └── schemas.py
│   └── lme_price_mcp/
│       ├── __init__.py
│       ├── server.py
│       ├── providers.py
│       └── schemas.py
├── data/
│   ├── fixtures/
│   │   ├── news.jsonl
│   │   ├── prices.csv
│   │   └── resources.json
│   └── samples/
│       └── pilbara_sample.txt
├── tests/
│   ├── test_news_server.py
│   ├── test_pdf_extractor.py
│   ├── test_price_server.py
│   └── test_agent_report.py
├── mcp-config.json
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── README.md
├── RUN.md
└── MCP_MINING_DAILY_AGENT_PLAN.md
```

## 4. 技术选型

### 4.1 语言

使用 Python。

理由：

1. MCP Python SDK 生态直接。
2. PDF 解析、数据清洗、CLI、测试都更快实现。
3. 适合 24 小时内完成可运行工程。

### 4.2 MCP server 实现

优先使用 Python MCP SDK / FastMCP 风格实现 stdio server。

每个 server 单独暴露工具：

1. `mining-news-mcp`
   - `search(query: str, days: int)`
   - `fetch_article(url: str)`
2. `mineral-pdf-mcp`
   - `extract_resources(pdf_url: str)`
3. `lme-price-mcp`
   - `get_price(commodity: str, date: str | null)`
   - `get_trend(commodity: str, days: int)`

### 4.3 Agent 编排

采用轻量自编排方案，不强依赖 LangGraph。

原因：

1. 题目重点是 MCP server + Agent，而不是复杂框架。
2. 自编排可控，减少 24 小时内的调试风险。
3. 更容易解释主流程和错误处理。

Agent 主流程：

```text
用户问题
  -> 解析主题、矿种、公司/项目名、时间范围
  -> 调 mining-news-mcp.search
  -> 对核心新闻调 mining-news-mcp.fetch_article
  -> 调 mineral-pdf-mcp.extract_resources
  -> 调 lme-price-mcp.get_price / get_trend
  -> 归并证据
  -> 生成 Markdown 简报
```

## 5. 三个 MCP Server 设计

## 5.1 mining-news-mcp

### 目标

提供矿业新闻搜索和文章详情获取能力。

### 工具 1：search(query, days)

输入：

```json
{
  "query": "Pilbara lithium",
  "days": 7
}
```

输出：

```json
{
  "items": [
    {
      "title": "Pilbara Minerals updates lithium operations",
      "url": "https://example.com/news/pilbara-lithium",
      "source": "fixture:mining-news",
      "published_at": "2026-06-12",
      "summary": "Short summary...",
      "matched_terms": ["Pilbara", "lithium"],
      "confidence": 0.86
    }
  ]
}
```

### 工具 2：fetch_article(url)

输入：

```json
{
  "url": "https://example.com/news/pilbara-lithium"
}
```

输出：

```json
{
  "title": "Pilbara Minerals updates lithium operations",
  "url": "https://example.com/news/pilbara-lithium",
  "source": "fixture:mining-news",
  "published_at": "2026-06-12",
  "text": "Full article text...",
  "citations": [
    {
      "label": "source",
      "url": "https://example.com/news/pilbara-lithium"
    }
  ]
}
```

### 数据策略

第一阶段使用 `data/fixtures/news.jsonl`，确保离线可跑。

后续可扩展真实 provider：

1. RSS provider：
   - mining.com RSS
   - S&P Global Mining RSS
2. HTML fetch provider：
   - requests + readability/html parser
3. 去重策略：
   - normalized URL
   - title hash
   - source + published date + title fingerprint

## 5.2 mineral-pdf-mcp

### 目标

从 NI 43-101 PDF 或 fixture 文本中抽取 Indicated / Inferred Resources。

### 工具：extract_resources(pdf_url)

输入：

```json
{
  "pdf_url": "https://example.com/pilbara-ni43101.pdf"
}
```

输出：

```json
{
  "project": "Pilbara lithium project",
  "document_url": "https://example.com/pilbara-ni43101.pdf",
  "resources": [
    {
      "category": "Indicated",
      "ore_tonnage_mt": 85.2,
      "grade": 1.23,
      "grade_unit": "% Li2O",
      "metal_content": 1.05,
      "metal_unit": "Mt Li2O",
      "evidence": "Table 14-3, Mineral Resource Estimate",
      "confidence": 0.82
    },
    {
      "category": "Inferred",
      "ore_tonnage_mt": 42.7,
      "grade": 1.08,
      "grade_unit": "% Li2O",
      "metal_content": 0.46,
      "metal_unit": "Mt Li2O",
      "evidence": "Table 14-3, Mineral Resource Estimate",
      "confidence": 0.77
    }
  ],
  "needs_human_review": false,
  "warnings": []
}
```

### 抽取策略

第一阶段：

1. 支持 fixture URL 映射到本地样例。
2. 对文本使用规则抽取：
   - 查找 `Indicated`
   - 查找 `Inferred`
   - 捕获 tonnage、grade、metal content、unit
3. 输出 evidence 和 confidence。

第二阶段可扩展：

1. 用 PyMuPDF 解析 PDF 文本。
2. 识别表格页。
3. 使用 LLM 做结构化抽取。
4. 加入 abstain 逻辑：
   - 字段缺失。
   - 单位冲突。
   - 数值不合理。
   - 无 evidence。

### 可靠性原则

如果抽取不确定，不硬给结论，返回：

```json
{
  "resources": [],
  "needs_human_review": true,
  "warnings": ["No reliable Indicated/Inferred resource table found."]
}
```

## 5.3 lme-price-mcp

### 目标

提供金属/矿产品价格点查和趋势分析。

### 工具 1：get_price(commodity, date)

输入：

```json
{
  "commodity": "lithium",
  "date": "2026-06-12"
}
```

输出：

```json
{
  "commodity": "lithium",
  "date": "2026-06-12",
  "price": 14300.0,
  "currency": "USD",
  "unit": "t",
  "source": "fixture:prices",
  "source_url": "https://example.com/prices/lithium"
}
```

### 工具 2：get_trend(commodity, days)

输入：

```json
{
  "commodity": "lithium",
  "days": 30
}
```

输出：

```json
{
  "commodity": "lithium",
  "days": 30,
  "start_price": 13800.0,
  "end_price": 14300.0,
  "change_abs": 500.0,
  "change_pct": 3.62,
  "direction": "up",
  "observations": [
    {
      "date": "2026-05-14",
      "price": 13800.0
    },
    {
      "date": "2026-06-12",
      "price": 14300.0
    }
  ],
  "source": "fixture:prices"
}
```

### 数据策略

第一阶段使用 `data/fixtures/prices.csv`。

字段：

```csv
date,commodity,price,currency,unit,source_url
2026-06-12,lithium,14300,USD,t,https://example.com/prices/lithium
```

后续可扩展：

1. LME copper/zinc/nickel provider。
2. SHFE lithium provider。
3. 上海钢联铁矿石 provider。
4. 缓存和频控。

## 6. Agent 输出设计

Agent 输入示例：

```text
给我生成一份关于 Pilbara 锂矿的今日简报
```

Agent 输出 Markdown：

```markdown
# Pilbara 锂矿今日简报

生成日期：2026-06-13

## 1. 新闻摘要

- Pilbara Minerals 近期更新锂矿运营情况，重点关注产量指引、成本控制和扩产节奏。[1]
- 近期市场报道显示，锂价波动仍受库存、下游电池需求和澳洲出口预期影响。[2]

## 2. 储量数据

| 分类 | 矿石量 | 品位 | 金属量 | 证据 |
| --- | ---: | ---: | ---: | --- |
| Indicated | 85.2 Mt | 1.23 % Li2O | 1.05 Mt Li2O | Table 14-3 |
| Inferred | 42.7 Mt | 1.08 % Li2O | 0.46 Mt Li2O | Table 14-3 |

## 3. 价格走势

锂价近 30 天从 13,800 USD/t 上升至 14,300 USD/t，涨幅约 3.62%，趋势为上行。

## 4. 风险提示

- 价格端：锂价对库存和电池需求变化敏感。
- 政策端：澳洲关键矿产政策和出口监管变化可能影响项目估值。
- 项目端：储量数据来自技术报告，仍需结合最新公告复核。

## 5. 引用源

[1] https://example.com/news/pilbara-lithium
[2] https://example.com/prices/lithium
[3] https://example.com/pilbara-ni43101.pdf
```

## 7. 工程化标准

### 7.1 配置

使用环境变量：

```text
DATA_DIR=data/fixtures
MCP_TRANSPORT=stdio
LOG_LEVEL=INFO
```

### 7.2 错误处理

所有工具失败时返回结构化错误：

```json
{
  "error": {
    "code": "ARTICLE_NOT_FOUND",
    "message": "No article matched the provided URL.",
    "details": {
      "url": "..."
    }
  }
}
```

原则：

1. 不静默吞异常。
2. 错误信息带上下文。
3. 不编造数据。
4. 缺失证据时标记 `needs_human_review`。

### 7.3 日志

日志包含：

1. 工具名。
2. 输入摘要。
3. 数据来源。
4. 耗时。
5. 错误原因。

避免记录：

1. API key。
2. 用户敏感信息。
3. 大段 PDF 原文。

### 7.4 测试

计划添加以下测试：

1. `test_news_server.py`
   - 搜索 Pilbara 能返回结果。
   - fetch 已知 URL 能返回全文。
   - fetch 不存在 URL 返回错误。
2. `test_pdf_extractor.py`
   - 能抽取 Indicated。
   - 能抽取 Inferred。
   - 无可靠表格时返回 human review。
3. `test_price_server.py`
   - 能获取指定日期价格。
   - 能计算 30 天趋势。
4. `test_agent_report.py`
   - 输入 Pilbara 简报请求。
   - 输出包含新闻、储量、价格、风险、引用。

## 8. mcp-config.json 设计

示例：

```json
{
  "mcpServers": {
    "mining-news-mcp": {
      "command": "python",
      "args": ["-m", "servers.mining_news_mcp.server"]
    },
    "mineral-pdf-mcp": {
      "command": "python",
      "args": ["-m", "servers.mineral_pdf_mcp.server"]
    },
    "lme-price-mcp": {
      "command": "python",
      "args": ["-m", "servers.lme_price_mcp.server"]
    }
  }
}
```

验收点：

1. Claude Desktop / Cursor 可以读取该配置。
2. 3 个 server 均可通过 stdio 启动。
3. 工具名与题面要求一致。

## 9. Docker 与运行方式

`docker-compose.yml` 计划提供一个默认 demo 服务：

```bash
docker compose up --build
```

容器启动后执行：

```bash
python -m agent.cli "给我生成一份关于Pilbara锂矿的今日简报"
```

`RUN.md` 中提供三种运行方式：

1. Docker Compose 一键运行。
2. 本地 Python 环境运行。
3. Claude Desktop / Cursor MCP 接入。

## 10. 24 小时实施排期

### 第 0-1 小时：仓库初始化

目标：

1. 初始化 Git。
2. 创建项目骨架。
3. 配置 `pyproject.toml`。
4. 配置基础 lint/test 命令。

验收：

1. `python -m pytest` 可执行。
2. 空项目结构清楚。

### 第 1-4 小时：实现 mining-news-mcp

目标：

1. 实现 `search(query, days)`。
2. 实现 `fetch_article(url)`。
3. 添加 `news.jsonl` fixture。
4. 添加单测。

验收：

1. 搜索 Pilbara/lithium 能返回新闻。
2. 返回结果包含 `title/url/source/published_at/summary`。
3. fetch 能返回全文和引用。

### 第 4-7 小时：实现 mineral-pdf-mcp

目标：

1. 实现 `extract_resources(pdf_url)`。
2. 添加 Pilbara 样例文本或 JSON fixture。
3. 实现 Indicated/Inferred 规则抽取。
4. 添加 human review fallback。

验收：

1. 能返回 Indicated 和 Inferred。
2. 每条数据包含矿石量、品位、金属量、单位、证据。
3. 无可靠证据时不硬给。

### 第 7-9 小时：实现 lme-price-mcp

目标：

1. 实现 `get_price(commodity, date)`。
2. 实现 `get_trend(commodity, days)`。
3. 添加 `prices.csv` fixture。
4. 添加趋势计算。

验收：

1. 支持 lithium/copper/nickel/zinc/iron_ore。
2. 能返回价格点。
3. 能返回 7/30 天趋势。

### 第 9-13 小时：实现 Agent 编排

目标：

1. 实现 `agent/orchestrator.py`。
2. 实现 CLI 输入。
3. 聚合 3 个 MCP server 数据。
4. 输出 Markdown 简报。

验收：

1. 输入 Pilbara 简报请求。
2. 输出包含新闻摘要、储量、价格、风险提示、引用源。
3. 数据来自工具返回，不凭空生成。

### 第 13-16 小时：补文档与配置

目标：

1. 写 `README.md`。
2. 写 `RUN.md`。
3. 写 `mcp-config.json`。
4. 写 `docker-compose.yml` 和 `Dockerfile`。

验收：

1. 评审可按 `RUN.md` 在 5 分钟内跑起来。
2. MCP 配置可直接复制到 Claude Desktop / Cursor。

### 第 16-20 小时：测试与修复

目标：

1. 补齐核心测试。
2. 跑端到端 demo。
3. 修复路径、依赖、编码、Docker 问题。

验收：

1. `python -m pytest` 通过。
2. `python -m agent.cli "给我生成一份关于Pilbara锂矿的今日简报"` 通过。
3. `docker compose up --build` 可运行。

### 第 20-24 小时：整理交付

目标：

1. 清理临时文件。
2. 检查 README/RUN 是否准确。
3. Git 提交。
4. 上传 GitHub。

验收：

1. 仓库结构清楚。
2. README 有项目说明。
3. RUN 有 5 分钟复现路径。
4. GitHub 页面可访问。

## 11. 验收清单

### 11.1 功能验收

| 项目 | 验收标准 |
| --- | --- |
| mining-news-mcp | 提供 `search` 和 `fetch_article` |
| mineral-pdf-mcp | 提供 `extract_resources` |
| lme-price-mcp | 提供 `get_price` 和 `get_trend` |
| Agent client | 输入中文需求，输出 Markdown 简报 |
| 引用源 | 新闻、价格、PDF 数据均有 source/source_url/evidence |
| 离线运行 | 无外网也能通过 fixture 跑通 |
| MCP 配置 | `mcp-config.json` 可接 Claude Desktop / Cursor |
| Docker | 一条 `docker compose` 命令可运行 |

### 11.2 工程验收

| 项目 | 验收标准 |
| --- | --- |
| 目录结构 | server/client/data/tests/docs 分层清楚 |
| 测试 | 覆盖核心工具和 Agent 简报 |
| 错误处理 | 返回结构化错误，不静默失败 |
| 可复现 | RUN 文档准确 |
| 可扩展 | fixture provider 和真实 provider 解耦 |
| 数据可信 | 输出带 evidence，不编造 |

## 12. 风险与应对

### 风险 1：MCP SDK 安装或版本不稳定

应对：

1. 固定依赖版本。
2. 保留最小 stdio server 实现路径。
3. Agent 端可用本地 provider fallback 完成 demo。

### 风险 2：评审环境没有网络

应对：

1. fixture-first。
2. Docker 镜像内包含样例数据。
3. RUN 文档明确离线模式。

### 风险 3：PDF 抽取不稳定

应对：

1. 第一版用 fixture 和规则抽取保证可演示。
2. 真实 PDF 作为扩展 provider。
3. 低置信度返回 human review。

### 风险 4：题目要求真实 MCP，而不是普通脚本

应对：

1. 3 个 server 均按 MCP 工具暴露。
2. 提供 `mcp-config.json`。
3. README 展示 Claude Desktop / Cursor 接入方式。
4. 测试中覆盖工具调用协议边界。

### 风险 5：Agent 输出像模板，不像真实编排

应对：

1. Agent 必须先调用新闻、PDF、价格工具。
2. Markdown 输出引用工具返回的字段。
3. 风险提示基于新闻主题、价格趋势和资源数据生成。

## 13. GitHub 提交策略

建议提交粒度：

```text
chore: initialize mining daily mcp agent project
feat: add mining news mcp server
feat: add mineral pdf resource extractor mcp server
feat: add price trend mcp server
feat: add mining daily agent orchestration
test: cover mcp tools and report generation
docs: add run guide and mcp desktop configuration
```

提交前检查：

```bash
python -m pytest
python -m agent.cli "给我生成一份关于Pilbara锂矿的今日简报"
docker compose up --build
```

## 14. 最小可演示路径

评审人员最短路径：

```bash
git clone <repo-url>
cd <repo>
docker compose up --build
```

期望看到：

1. 3 个 MCP server 可启动。
2. Agent 生成 Pilbara 锂矿 Markdown 简报。
3. 输出包含：
   - 新闻摘要。
   - Indicated/Inferred 储量数据。
   - 锂价趋势。
   - 风险提示。
   - 引用源链接。

## 15. 当前阶段说明

当前文档是实施计划，还未创建代码项目。

后续执行前建议：

1. 在当前项目目录初始化 Git。
2. 创建 checkpoint commit。
3. 按本计划逐步实现。
4. 每个阶段跑测试，避免最后集中排错。

外部检索状态：未实际检索外部资料；本计划仅基于题面、本地上下文和通用 MCP/Python 工程经验制定。

