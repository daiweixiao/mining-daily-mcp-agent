# MCP 矿权日报 Agent — `mining-daily-mcp-agent`

> 基于 **MCP (Model Context Protocol)** 的「矿权日报 Agent」。题 #2 实现：**3 个独立 MCP Server + 1 个 Client 端 Agent 编排程序**，输入一句中文需求，输出一份带证据与引用源的 Markdown 矿权日报。
>
> 设计原则：**fixture-first（离线可复现）、evidence-based（带证据不编造）、live-capable（可平滑接入真实数据源）**。无外网、无 API key 也能在 5 分钟内跑通。

---

## 目录

1. [项目简介](#1-项目简介)
2. [功能亮点](#2-功能亮点)
3. [系统架构与数据流](#3-系统架构与数据流)
4. [完整目录结构（逐文件说明）](#4-完整目录结构逐文件说明)
5. [环境要求与安装](#5-环境要求与安装)
6. [5 分钟快速开始](#6-5-分钟快速开始)
7. [命令行（CLI）用法](#7-命令行cli用法)
8. [三个 MCP Server 详解](#8-三个-mcp-server-详解)
9. [Agent 编排流程详解](#9-agent-编排流程详解)
10. [统一数据契约](#10-统一数据契约)
11. [Fixture 数据说明](#11-fixture-数据说明)
12. [Live 真实数据源模式](#12-live-真实数据源模式)
13. [可选 LLM 增强](#13-可选-llm-增强)
14. [Docker 运行](#14-docker-运行)
15. [测试（15 个用例逐一说明）](#15-测试15-个用例逐一说明)
16. [MCP 客户端接入](#16-mcp-客户端接入claude-code--desktop--cursor)
17. [环境变量参考总表](#17-环境变量参考总表)
18. [设计决策与 FAQ](#18-设计决策与-faq)
19. [题 #2 验收对照表](#19-题-2-验收对照表)
20. [已知边界与后续规划](#20-已知边界与后续规划)

---

## 1. 项目简介

本项目实现招聘题 **#2：MCP 矿权日报 Agent**。它把「矿业新闻 / NI 43-101 储量报告 / 金属价格」三类数据源分别封装成 3 个符合 MCP 协议的 stdio server，再由一个 client 端 Agent 负责解析用户意图、按顺序调用这些 MCP 工具、归并证据并渲染成中文 Markdown 日报。

| 组件 | 名称 | 角色 | 暴露的 MCP 工具 |
| --- | --- | --- | --- |
| MCP Server 1 | `mining-news-mcp` | 矿业新闻搜索与正文抓取 | `search(query, days)`、`fetch_article(url)` |
| MCP Server 2 | `mineral-pdf-mcp` | NI 43-101 储量（Indicated/Inferred）抽取 | `extract_resources(pdf_url)` |
| MCP Server 3 | `lme-price-mcp` | 金属/矿产品价格点查与趋势 | `get_price(commodity, date)`、`get_trend(commodity, days)` |
| Client Agent | `agent` | 编排上述工具，生成 Markdown 日报 | —（消费方） |

**为什么默认 fixture-first？** 评审环境可能无外网、无 API key、有频控。项目内置 `data/fixtures/` 离线样例数据，保证一条命令稳定复现；同时所有 provider 都做了 live/fixture 解耦，真实 RSS、远程 PDF、价格 API/CSV 可通过环境变量平滑接入。

---

## 2. 功能亮点

- **真实 MCP，而非普通脚本**：3 个 server 均用 MCP Python SDK 的 `FastMCP` 以 stdio 暴露工具；Agent 通过 `mcp.client.stdio` 真正建立会话、`call_tool` 调用，并解析 `structuredContent`。
- **两种 transport 可切换**：`local`（进程内直接调 provider，零依赖、利于测试与离线演示）与 `mcp`（标准 MCP stdio 协议，用于正式演示与客户端接入）。两条路径复用同一套 provider 逻辑。
- **证据优先，不编造**：每条储量数据带 `evidence` 与 `confidence`；价格带 `source_url`；新闻带 `citations`。证据不足时返回结构化错误或 `needs_human_review=true`，绝不硬给结论。
- **live / fixture 自动降级**：`auto` 模式优先尝试真实数据源，失败时回退 fixture 并在结果里写明 `fallback_reason`，可追溯。
- **中英文意图解析**：支持「锂/锂矿/铜/锌/镍/铁矿石」与英文别名，支持「近 N 天 / N days」时间窗解析。
- **可选 LLM 润色**：先用 MCP 工具拿到结构化证据，再（可选）调用 OpenAI 兼容模型润色中文；模型失败自动回退规则版。
- **工程化完整**：分层目录、15 个单测、Dockerfile + docker-compose、`.mcp.json` / `mcp-config.json` 客户端配置、健康检查脚本、`.env` 自动加载。
- **零三方依赖即可离线运行**：核心逻辑仅用 Python 标准库（`urllib`/`xml`/`csv`/`html.parser`）；`mcp` 仅在使用 MCP transport 时需要，`pymupdf` 仅在解析真实 PDF 时需要。

---

## 3. 系统架构与数据流

### 3.1 组件关系

```text
                          用户一句话需求
            "给我生成一份关于Pilbara锂矿的今日简报"
                               │
                               ▼
                    ┌──────────────────────┐
                    │   agent/cli.py       │  解析参数 / 选择 transport / 落盘
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │ agent/orchestrator.py│  parse_request → 调工具 → 归并证据
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │  agent/mcp_client.py │  抽象工具客户端（两种实现）
                    └───┬──────────────┬───┘
          local transport│              │mcp transport (stdio)
                         ▼              ▼
          进程内直接调 provider    spawn `python -m servers.*.server`
                         │              │  （MCP ClientSession.call_tool）
                         └──────┬───────┘
                                ▼
        ┌───────────────┬───────────────┬────────────────┐
        ▼               ▼               ▼                │
  mining-news-mcp  mineral-pdf-mcp   lme-price-mcp        │
   search/fetch    extract_resources  get_price/trend     │
        │               │               │                │
        ▼               ▼               ▼                │
  Hybrid provider  ResourceExtractor  Hybrid provider     │
  live:rss/html │  fixture/local/     manual_csv/         │
  fixture:jsonl │  remote pdf         live:http/fixture   │
        └───────────────┴───────────────┴────────────────┘
                                ▼
                    ┌──────────────────────┐
                    │  agent/renderer.py   │  渲染 5 段式 Markdown
                    └──────────┬───────────┘
                               ▼
                    ┌──────────────────────┐
                    │   agent/llm.py       │  （可选）LLM 润色，失败回退
                    └──────────┬───────────┘
                               ▼
              Markdown 日报 → stdout + reports/mining_daily_<ts>.md
```

### 3.2 端到端流程（与代码一一对应）

1. `agent/cli.py:main` 配置 UTF-8 输出、加载 `.env`、解析 CLI 参数，按 `--transport` 实例化 `LocalToolClient` 或 `StdioMCPToolClient`。
2. `agent/orchestrator.py:generate_report` 调用 `parse_request` 解析出 `project`、`commodity`、`news_days`、`price_days`。
3. 调 `search_news(f"{project} {commodity}", news_days)`，对前 3 条新闻逐条 `fetch_article`（跳过报错项）。
4. 解析储量报告 URL（`RESOURCE_PDF_URL` 环境变量 → 项目映射 → 默认 fixture），调 `extract_resources`。
5. 调 `get_price(commodity)` 与 `get_trend(commodity, price_days)`。
6. `agent/renderer.py:render_report` 把以上证据渲染成 5 段式 Markdown。
7. `agent/llm.py:enhance_report` 视配置决定是否 LLM 润色（默认关闭，直接返回规则版）。
8. CLI 把报告打印到 stdout，并写入 `reports/mining_daily_<timestamp>.md`（或 `--output` 指定路径）。

---

## 4. 完整目录结构（逐文件说明）

```text
mining-daily-mcp-agent/
├── agent/                          # ── Client 端 Agent 编排 ──
│   ├── __init__.py                 # 包标识
│   ├── cli.py                      # CLI 入口：参数解析、transport 选择、报告落盘
│   ├── orchestrator.py             # 核心编排：意图解析 + 顺序调用 5 个工具 + 归并
│   ├── mcp_client.py               # 工具客户端抽象：LocalToolClient / StdioMCPToolClient
│   ├── renderer.py                 # 规则渲染器：把证据渲染成 5 段式 Markdown
│   ├── llm.py                      # 可选 LLM 润色（OpenAI 兼容），失败安全回退
│   ├── schemas.py                  # ReportRequest dataclass 等数据结构
│   └── healthcheck.py              # 数据源健康检查脚本（不生成报告，只打印各源状态）
│
├── servers/                        # ── 3 个 MCP Server ──
│   ├── __init__.py
│   ├── mining_news_mcp/
│   │   ├── __init__.py
│   │   ├── server.py               # FastMCP server，暴露 search / fetch_article
│   │   └── providers.py            # HybridNewsProvider（live:rss/html + fixture:jsonl）
│   ├── mineral_pdf_mcp/
│   │   ├── __init__.py
│   │   ├── server.py               # FastMCP server，暴露 extract_resources
│   │   └── extractor.py            # ResourceExtractor + 正则抽取 + PyMuPDF + 远程下载
│   └── lme_price_mcp/
│       ├── __init__.py
│       ├── server.py               # FastMCP server，暴露 get_price / get_trend
│       └── providers.py            # HybridPriceProvider（manual_csv + live:http + fixture:csv）
│
├── data/                           # ── 数据 ──
│   ├── fixtures/                   # 离线确定性样例（默认数据源）
│   │   ├── news.jsonl              # 8 条矿业新闻（JSONL）
│   │   ├── prices.csv              # 5 种商品 × 5 个日期的价格序列
│   │   └── resources.json          # Pilgangoora NI 43-101 Indicated/Inferred 储量
│   └── samples/                    # 仅用于测试/演示 live 解析路径的样例
│       ├── pilbara_sample.txt      # 储量表纯文本，验证文本抽取
│       ├── article_sample.html     # 文章 HTML，验证正文抽取
│       └── rss_sample.xml          # RSS 样例，验证 RSS 解析
│
├── tests/                          # ── 15 个单元测试 ──
│   ├── conftest.py                 # autouse fixture：强制确定性环境（关闭 live/LLM）
│   ├── test_news_server.py         # 新闻：搜索/抓取/错误/live 文件源（4）
│   ├── test_pdf_extractor.py       # 储量：fixture 抽取 / 不完整标记 review（2）
│   ├── test_price_server.py        # 价格：点查 / 趋势 / 手动 CSV（3）
│   ├── test_agent_report.py        # Agent：端到端 Markdown / 规则版（2）
│   ├── test_cli_output.py          # CLI：自动落盘 / 指定 --output（2）
│   └── test_llm.py                 # LLM：启用润色 / 失败回退（2）
│
├── examples/
│   └── pilbara_daily_report.md     # 一份示例输出报告（可直接预览效果）
│
├── reports/                        # CLI 自动生成的报告（被 .gitignore 忽略，运行后出现）
│
├── project_env.py                  # 轻量 .env 加载器（不覆盖已有真实环境变量）
├── pyproject.toml                  # 构建/依赖/pytest 配置
│
├── .mcp.json                       # Claude Code 项目级 MCP 配置（本机绝对路径）
├── mcp-config.json                 # Claude Desktop / Cursor 通用 MCP 配置（fixture）
├── mcp-config.live.example.json    # Claude Desktop / Cursor live 模式配置示例
│
├── Dockerfile                      # python:3.12-slim，安装 [dev,live]，默认 mcp transport
├── docker-compose.yml              # 默认服务 + live profile 服务
│
├── .env.example                    # 环境变量模板（复制为 .env 使用）
├── .gitignore                      # 忽略 .venv/缓存/.env/reports/*.md 等
├── .gitattributes                  # 统一文本文件 eol=lf
│
├── README.md                       # 本文档
├── RUN.md                          # 5 分钟复现指南（含一条 docker compose 命令）
├── DATA_SOURCE_NOTES.md            # 数据源接入细节（live/fixture、CSV/JSON schema）
└── MCP_MINING_DAILY_AGENT_PLAN.md  # 选题理由 + 24h 实施计划 + 验收清单
```

> **说明**：`reports/` 目录在首次运行 CLI 后才会出现；其中的 `*.md` 已被 `.gitignore` 忽略，避免把每天生成的日报误提交。

---

## 5. 环境要求与安装

- **Python ≥ 3.11**（`pyproject.toml` 中 `requires-python = ">=3.11"`；Docker 镜像用 3.12）。
- **核心依赖**：`mcp >= 1.9.0`（仅 `mcp` transport 与启动 server 时需要）。
- **可选 extras**：
  - `dev`：`pytest >= 8.0`（跑测试）。
  - `live`：`pymupdf >= 1.24.0`（解析真实 PDF）。

```bash
# 基础安装（含 MCP）
pip install -e .

# 推荐：开发 + 测试
pip install -e ".[dev]"

# 需要解析真实 PDF 时
pip install -e ".[dev,live]"
```

> **离线纯演示**：若只用 `--transport local`，连 `mcp` 都不是必需的——核心 provider 全部基于标准库。但安装 `mcp` 后才能体验真正的 MCP stdio 协议路径。

---

## 6. 5 分钟快速开始

### 路径 A：本地 Python（最快）

```bash
pip install -e ".[dev]"
python -m agent.cli "给我生成一份关于Pilbara锂矿的今日简报"
```

默认 `--transport local`，进程内直接调 fixture provider，无需任何网络或 key。

### 路径 B：走真正的 MCP stdio 协议

```bash
python -m agent.cli --transport mcp "给我生成一份关于Pilbara锂矿的今日简报"
```

Agent 会按需 `spawn` 三个 server 子进程，通过 MCP `ClientSession.call_tool` 调用工具。

### 路径 C：Docker 一键运行

```bash
docker compose up --build
```

容器默认 `--transport mcp`，启动后直接输出一份 Pilbara 锂矿日报。

### 落盘查看

```bash
python -m agent.cli --transport mcp --output examples/pilbara_daily_report.md "给我生成一份关于Pilbara锂矿的今日简报"
```

> **Windows PowerShell 提示**：若报告含 `Li2O` 等 Unicode 下标符号导致编码报错，用 `python -X utf8 -B -m agent.cli ...`。

---

## 7. 命令行（CLI）用法

### 7.1 `agent.cli`

```bash
python -m agent.cli [--transport local|mcp] [--data-dir PATH] [--output PATH] ["你的需求"]
```

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `prompt`（位置参数） | `给我生成一份关于Pilbara锂矿的今日简报` | 用户需求，中文/英文均可 |
| `--transport` | 环境变量 `AGENT_TRANSPORT` 或 `local` | `local`=进程内 provider；`mcp`=MCP stdio 协议 |
| `--data-dir` | 环境变量 `DATA_DIR` 或 `data/fixtures` | fixture 数据目录 |
| `--output` | `reports/mining_daily_<时间戳>.md` | 指定报告写入路径 |

行为：报告同时打印到 **stdout**；保存路径打印到 **stderr**（`Saved report to ...`）。

### 7.2 `agent.healthcheck`

不生成报告，只打印各数据源当前返回与关键环境变量，用于排查 live 接入。

```bash
python -m agent.healthcheck --query "Pilbara lithium" --commodity lithium --days 7
```

| 参数 | 默认值 |
| --- | --- |
| `--query` | `Pilbara lithium` |
| `--commodity` | `lithium` |
| `--days` | `7` |
| `--data-dir` | `DATA_DIR` 或 `data/fixtures` |
| `--pdf-url` | `RESOURCE_PDF_URL` 或 `fixture://reports/pilbara-ni-43-101` |

输出为 JSON，含 `news` / `resources` / `price` / `trend` 四块结果，以及 `env`（`LIVE_MODE`、`NEWS_MODE`、`PRICE_MODE`、`NEWS_RSS_URLS`、`PRICE_CSV_PATH`、`PRICE_API_URL`、`RESOURCE_PDF_URL`）。

---

## 8. 三个 MCP Server 详解

每个 server 都可独立以 stdio 启动：

```bash
python -m servers.mining_news_mcp.server
python -m servers.mineral_pdf_mcp.server
python -m servers.lme_price_mcp.server
```

实现统一采用 `FastMCP("<server-name>")` + `@mcp.tool()` 装饰器，运行 `transport="stdio"`。所有工具返回 **结构化 JSON dict**。

### 8.1 `mining-news-mcp`

矿业新闻搜索与正文抓取。由 `HybridNewsProvider` 实现 **live-first + fixture fallback**：

- `mode` = 环境变量 `NEWS_MODE`，否则 `LIVE_MODE` 为真时 `live`、否则 `fixture`。
- `fixture` 模式：纯读 `data/fixtures/news.jsonl`。
- `live` / `auto` 模式：先抓 RSS；`auto` 在 live 无结果时回退 fixture 并写 `fallback_reason`，`live` 严格只用 live。
- `fetch_article`：URL 以 `fixture://` 开头或 fixture 模式 → 读 fixture；否则抓 HTML 用标准库解析正文。

#### 工具 `search(query, days=7)`

输入：

```json
{ "query": "Pilbara lithium", "days": 7 }
```

fixture 输出（节选）：

```json
{
  "items": [
    {
      "title": "Pilbara Minerals reports stable Pilgangoora operating performance",
      "url": "https://www.pilbaraminerals.com.au/investors/asx-announcements/",
      "source": "fixture:mining-news",
      "published_at": "2026-06-12",
      "summary": "Pilbara Minerals' latest operating update points to steady ...",
      "matched_terms": ["lithium", "pilbara"],
      "confidence": 0.86
    }
  ],
  "query": "Pilbara lithium",
  "days": 7,
  "source": "fixture:news.jsonl"
}
```

| 字段 | 含义 |
| --- | --- |
| `items[].title/url/source/published_at/summary` | 标题/链接/来源标签/发布日期/摘要 |
| `items[].matched_terms` | 命中的查询词（中文别名会归一为英文） |
| `items[].confidence` | 置信度；fixture：`min(0.99, 0.55 + 命中率×0.4)`；live：`min(0.98, 0.52 + 命中率×0.42)` |
| `source` | `fixture:news.jsonl` / `live:rss` |
| `rss_urls`（live） | 实际抓取的 RSS 列表 |
| `warnings`（live） | 单个 RSS 抓取失败的结构化记录 |
| `fallback_reason`（auto 回退时） | 回退原因，如 `{"code":"LIVE_EMPTY",...}` |

排序：fixture 取命中分 Top 8，live 去重后取 Top 10（按 confidence 与日期降序）。去重键为去掉 query 串与尾斜杠的 URL。

#### 工具 `fetch_article(url)`

成功输出：

```json
{
  "title": "...",
  "url": "https://...",
  "source": "fixture:mining-news",
  "published_at": "2026-06-12",
  "summary": "...",
  "text": "全文...",
  "citations": [{ "label": "fixture:mining-news", "url": "https://..." }]
}
```

错误（结构化，不抛异常）：

| `error.code` | 触发条件 |
| --- | --- |
| `ARTICLE_NOT_FOUND` | fixture 中无匹配 URL |
| `ARTICLE_FETCH_FAILED` | live HTTP 抓取失败 |
| `ARTICLE_TEXT_EMPTY` | 抓到页面但抽不出正文 |

> live 正文抽取使用自定义 `_ReadableHTMLParser`：跳过 `script/style/nav/footer` 等噪声标签，提取 `p/li/h1-h3/td/article/section` 文本，`<title>` 作为标题。

### 8.2 `mineral-pdf-mcp`

从 NI 43-101 报告中抽取 **Indicated / Inferred** 资源量。由 `ResourceExtractor.extract_resources(pdf_url)` 实现，输入解析优先级：

1. **fixture URL**（命中 `resources.json` 的 key，如 `fixture://reports/pilbara-ni-43-101`）→ 直接返回结构化储量。
2. **远程 `http(s)`** → 下载；按 Content-Type/后缀判定 PDF 或文本；PDF 用 PyMuPDF 抽文本。
3. **本地 `.txt` / `.md`** → 直接读取。
4. **本地 `.pdf`** → PyMuPDF 抽文本。
5. 其他 → `DOCUMENT_NOT_FOUND`。
6. 拿到文本后用正则抽取；**抽不到表格或不足 2 行**时返回 `needs_human_review=true`。

#### 工具 `extract_resources(pdf_url)`

fixture 输出：

```json
{
  "project": "Pilgangoora Operation (Pilbara Minerals)",
  "document_url": "fixture://reports/pilbara-ni-43-101",
  "source_url": "https://www.pilbaraminerals.com.au/",
  "resources": [
    {
      "category": "Indicated",
      "ore_tonnage_mt": 85.2,
      "grade": 1.23,
      "grade_unit": "% Li2O",
      "metal_content": 1.05,
      "metal_unit": "Mt Li2O",
      "evidence": "Fixture technical report summary, Table 14-3",
      "confidence": 0.82
    },
    { "category": "Inferred", "ore_tonnage_mt": 42.7, "grade": 1.08, "...": "..." }
  ],
  "needs_human_review": false,
  "warnings": []
}
```

| 字段 | 含义 |
| --- | --- |
| `category` | `Indicated` / `Inferred`（`Measured and/& Indicated` 会归一为 `Indicated`） |
| `ore_tonnage_mt` | 矿石量，统一换算为 Mt（kt÷1000、tonnes÷1e6） |
| `grade` / `grade_unit` | 品位与单位（如 `% Li2O`、`g/t Au`） |
| `metal_content` / `metal_unit` | 金属量与单位（如 `Mt Li2O`、`koz`） |
| `evidence` | 命中位置前后约 ±80 字符的原文片段（≤260 字符） |
| `confidence` | fixture 沿用样例值；文本抽取固定 `0.68` |
| `needs_human_review` | 文本抽取结果 `< 2` 行即为 `true` |

抽取不到时返回：

```json
{
  "project": "unknown",
  "document_url": "...",
  "source_url": "...",
  "resources": [],
  "needs_human_review": true,
  "warnings": ["No reliable Indicated/Inferred table found."]
}
```

| `error.code`（远程/PDF 相关） | 触发条件 |
| --- | --- |
| `DOCUMENT_NOT_FOUND` | 非 fixture 且非可识别的本地文本/PDF 路径 |
| `DOCUMENT_FETCH_FAILED` | 远程下载失败 |
| `PDF_READER_UNAVAILABLE` | 未安装 PyMuPDF（需 `pip install -e ".[live]"`） |
| `PDF_TEXT_EXTRACTION_FAILED` | PDF 解析异常 |

### 8.3 `lme-price-mcp`

金属/矿产品价格点查与趋势。由 `HybridPriceProvider` 实现 **manual_csv → live:http → fixture** 的优先级：

- `mode` = `PRICE_MODE`，否则 `LIVE_MODE` 为真时 `live`、否则 `fixture`。
- 配置了 `PRICE_CSV_PATH` 启用手动 CSV provider；配置了 `PRICE_API_URL` 启用通用 JSON API provider。
- 非 fixture 模式按顺序尝试 manual、http；`auto` 全部失败回退 fixture 并写 `fallback_reason`，`live` 严格只用 live/manual。
- 商品名归一：支持 `li/锂/锂矿、cu/铜、zn/锌、ni/镍、iron ore/铁矿石` 等别名。

#### 工具 `get_price(commodity, date=None)`

```json
{
  "commodity": "lithium",
  "date": "2026-06-12",
  "price": 14300.0,
  "currency": "USD",
  "unit": "t",
  "source": "fixture:prices",
  "source_url": "https://www.lme.com/Metals/EV/LME-Lithium-Hydroxide-CIF-Fastmarkets-MB"
}
```

逻辑：按商品过滤 → 无则 `COMMODITY_NOT_FOUND` → 取 `≤ 目标日期` 中最新一条 → 都没有则 `PRICE_NOT_FOUND`。未传 `date` 取该商品最新日期。

#### 工具 `get_trend(commodity, days=30)`

```json
{
  "commodity": "lithium",
  "days": 30,
  "start_date": "2026-05-14",
  "end_date": "2026-06-12",
  "start_price": 13800.0,
  "end_price": 14300.0,
  "change_abs": 500.0,
  "change_pct": 3.62,
  "direction": "up",
  "currency": "USD",
  "unit": "t",
  "observations": [
    { "date": "2026-05-14", "price": 13800.0 },
    { "date": "2026-06-12", "price": 14300.0 }
  ],
  "source": "fixture:prices.csv"
}
```

| 字段 | 含义 |
| --- | --- |
| `change_pct` | 涨跌幅（%） |
| `direction` | `up`（>0.5%）/ `down`（<-0.5%）/ `flat` |
| `observations` | 时间窗内全部观测点 |
| 错误 `TREND_UNAVAILABLE` | 该商品价格点 < 2 条 |

---

## 9. Agent 编排流程详解

### 9.1 意图解析 `parse_request(prompt)`

| 解析项 | 规则 | 默认 |
| --- | --- | --- |
| `project` | 正则匹配 `pilbara\|pilgangoora\|newmont\|barrick` 并 `.title()` | `Pilbara` |
| `commodity` | 查 `COMMODITY_ALIASES`（中英）命中即归一 | `lithium` |
| `news_days` | 正则 `近\s*(\d+)\s*天` 或 `(\d+)\s*days?` | `7` |
| `price_days` | 固定 | `30` |

### 9.2 编排步骤 `MiningDailyAgent.generate_report`

```text
1. load_dotenv()                                # 加载 .env（不覆盖已有环境变量）
2. request = parse_request(prompt)              # 解析意图
3. news = search_news(f"{project} {commodity}", news_days)
4. for item in news.items[:3]:                  # 取前 3 条
       article = fetch_article(item.url)
       if "error" not in article: articles.append(article)
5. resource_url = RESOURCE_PDF_URL              # 环境变量优先
                  or PROJECT_RESOURCE_URLS[project]  # 项目映射
                  or "fixture://reports/pilbara-ni-43-101"  # 默认
   resources = extract_resources(resource_url)
6. price = get_price(commodity)
   trend = get_trend(commodity, price_days)
7. base = render_report(request, news, articles, resources, price, trend)
8. return enhance_report(base, evidence)        # 默认直接返回规则版
```

### 9.3 渲染输出结构 `render_report`

固定 5 段式 Markdown：

```text
# {project} {Commodity} 矿权日报
生成日期：YYYY-MM-DD

## 1. 新闻摘要      —— 前 3 条新闻摘要 + 角标引用，无则提示人工补充
## 2. 储量数据      —— Markdown 表格（分类/矿石量/品位/金属量/证据）；
                       needs_human_review 时改为提示 + warnings
## 3. 价格走势      —— 自然语言描述近 N 天涨跌幅与方向 + 最新价格
## 4. 风险提示      —— 基于价格方向 + 资源可信度 + 新闻覆盖动态生成
## 5. 引用源        —— 去重后的新闻/储量/价格来源链接

> 数据来源：news=...; resources=...; price=...; [fallback=...]
```

风险提示是**动态**的（见 `_build_risks`）：价格上行/下行/持平给不同措辞；储量 `needs_human_review` 时提示人工复核；新闻缺失时提示补充公告。数字格式化 `_format_number`：≥100 取千分位整数，否则保留 2 位并去尾零。

---

## 10. 统一数据契约

- **结构化返回**：所有工具返回 JSON dict，便于 Agent 与任意 MCP 客户端消费。
- **结构化错误**：失败时返回 `{"error": {"code": "...", "message": "...", "details": {...}}}`，**不静默吞异常、不抛栈**。
- **证据与来源**：新闻带 `citations`，储量带 `evidence`，价格带 `source_url`，并都带 `source` 标签（`fixture:*` / `live:*` / `manual_csv`）。
- **不编造**：证据不足时 `needs_human_review=true` 或返回错误，渲染层据此降级展示。
- **可追溯回退**：live 失败回退 fixture 时写 `fallback_reason`，并由渲染层汇总进「数据来源」脚注。

---

## 11. Fixture 数据说明

| 文件 | 内容 | 关键点 |
| --- | --- | --- |
| `data/fixtures/news.jsonl` | 8 条矿业新闻（每行一个 JSON） | 含 `title/url/source/published_at/summary/text/tags`，覆盖 Pilbara 运营、关键矿产政策、锂价、融资、基础设施等主题 |
| `data/fixtures/prices.csv` | 5 商品 × 5 日期价格序列 | `lithium/copper/zinc/nickel/iron_ore`，日期 2026-05-14 → 2026-06-12；列 `date,commodity,price,currency,unit,source,source_url` |
| `data/fixtures/resources.json` | Pilgangoora NI 43-101 储量 | `documents` 字典，key 为 fixture URL，含 Indicated/Inferred 两行 |
| `data/samples/pilbara_sample.txt` | 储量表纯文本 | 验证「文本 → 正则抽取」路径 |
| `data/samples/article_sample.html` | 文章 HTML | 验证正文抽取 |
| `data/samples/rss_sample.xml` | RSS 样例 | 验证 RSS 解析 |

> fixture 搜索的「参考日期」取自 fixture 内最大 `published_at`，因此即使系统时间漂移，`days` 时间窗依然能稳定命中样例数据——这是离线可复现的关键设计。

---

## 12. Live 真实数据源模式

`auto` 模式 = live 优先 + fixture 兜底；`live` 模式 = 严格只用真实源。

### 12.1 新闻 RSS / 正文

```bash
LIVE_MODE=true NEWS_MODE=auto NEWS_RSS_URLS="https://www.mining.com/feed/" \
python -m agent.cli --transport mcp "给我生成一份关于Pilbara锂矿的今日简报"
```

- 读取 RSS（支持 RSS 2.0 `<item>` 与 Atom `<entry>`），按 query 与时间窗过滤，抓取正文，按规范化 URL 去重，来源标 `live:rss` / `live:html`。

### 12.2 储量 PDF

```bash
pip install -e ".[live]"
RESOURCE_PDF_URL="https://example.com/path/to/ni-43-101.pdf" \
python -m agent.cli --transport mcp "给我生成一份关于Pilbara锂矿的今日简报"
```

- 支持 fixture URL、本地 `.txt/.md`、本地 `.pdf`、远程 `http(s)`；PDF 解析需 PyMuPDF；失败返回 `needs_human_review=true`。

### 12.3 价格 CSV / API

```bash
# 手动授权 CSV
PRICE_MODE=auto PRICE_CSV_PATH=/path/to/prices.csv \
python -m agent.cli --transport mcp "..."

# 通用 JSON API（URL 支持 {commodity}/{date}/{days} 占位符）
PRICE_MODE=auto PRICE_API_URL="https://price-api.example.com/prices?commodity={commodity}&date={date}&days={days}" \
python -m agent.cli --transport mcp "..."
```

- CSV schema：`date,commodity,price,currency,unit,source,source_url`。
- JSON API 可返回单对象或 `list` / `items` / `observations` 数组，字段同上。
- 因 LME / SHFE / Mysteel 多需授权或登录，项目**不硬编脆弱爬虫**，而是接受授权后的 API/CSV 输入，并保留 fixture 兜底。

> 更多细节见 `DATA_SOURCE_NOTES.md`；live 客户端配置示例见 `mcp-config.live.example.json`。检查当前数据源：`python -m agent.healthcheck`。

---

## 13. 可选 LLM 增强

题 #2 **不强制依赖 LLM**，默认关闭以保证离线可复现。启用后，Agent 先用 MCP 工具拿到结构化证据，再调用 OpenAI 兼容模型润色中文摘要与风险提示；**模型失败/输出不完整会自动回退规则版**（在 `agent/llm.py:enhance_report`）。

在 `.env` 中：

```text
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-v4-flash
OPENAI_API_KEY=replace-with-your-api-key
LLM_ENABLED=true
LLM_MAX_TOKENS=1800
LLM_TEMPERATURE=0.2
LLM_TIMEOUT_SECONDS=60
```

启用条件：`LLM_ENABLED` 为真值 **且** `OPENAI_API_KEY` 非空。系统提示明确要求模型「保留所有数字、链接、标题与引用，不得添加无依据结论，证据弱要明说」。

---

## 14. Docker 运行

```bash
# 默认（fixture + mcp transport）
docker compose up --build

# live profile（启用真实新闻 RSS，仍带 fixture 兜底）
docker compose --profile live up --build mining-daily-agent-live
```

- 镜像：`python:3.12-slim`，安装 `-e ".[dev,live]"`（含 PyMuPDF 与 pytest）。
- 默认环境：`DATA_DIR=/app/data/fixtures`、`AGENT_TRANSPORT=mcp`。
- 默认命令直接生成一份 Pilbara 锂矿日报到 stdout。

---

## 15. 测试（15 个用例逐一说明）

```bash
python -m pytest          # 全部 15 个用例
```

`tests/conftest.py` 用 autouse fixture 强制确定性环境（`LLM_ENABLED=false`、`LIVE_MODE=false`、`NEWS_MODE/PRICE_MODE=fixture`，清空 live 相关变量），即使本机 `.env` 开了 live 也不影响测试稳定性。

| 文件 | 用例 | 验证点 |
| --- | --- | --- |
| `test_news_server.py` | `test_search_returns_pilbara_lithium_news` | 搜索 Pilbara lithium 有结果、有 title/url、confidence≥0.55 |
| | `test_fetch_article_returns_text` | 抓取命中文章返回全文且 citation URL 一致 |
| | `test_fetch_missing_article_returns_structured_error` | 不存在 URL 返回 `ARTICLE_NOT_FOUND` |
| | `test_live_news_provider_reads_file_rss_and_article` | live provider 从 `file://` RSS+HTML 解析，来源标 `live:rss`/`live:html` |
| `test_pdf_extractor.py` | `test_fixture_extracts_indicated_and_inferred` | fixture 抽出 Indicated+Inferred 且不需人工复核 |
| | `test_text_extractor_marks_incomplete_result_for_review` | 仅 1 行时标记 `needs_human_review=true` |
| `test_price_server.py` | `test_get_latest_lithium_price` | 中文「锂」归一为 lithium，取最新价 14300/2026-06-12 |
| | `test_get_lithium_trend` | 30 天趋势方向 up、涨幅>0、≥2 观测点 |
| | `test_manual_csv_price_provider` | 手动 CSV provider 点查与趋势 |
| `test_agent_report.py` | `test_agent_generates_markdown_report` | 端到端报告含全部 5 段与 Indicated/Inferred |
| | `test_agent_uses_rule_renderer_when_llm_disabled` | LLM 关闭时走规则版、含「数据来源」 |
| `test_cli_output.py` | `test_cli_auto_saves_report` | 默认自动写 `reports/mining_daily_*.md` 并在 stderr 提示 |
| | `test_cli_respects_explicit_output_path` | `--output` 指定路径时不写默认目录 |
| `test_llm.py` | `test_llm_enhancement_can_be_enabled_without_network` | mock 模型返回，启用润色生效 |
| | `test_llm_enhancement_falls_back_on_error` | 模型抛错时回退规则版并附「LLM 增强失败」 |

---

## 16. MCP 客户端接入（Claude Code / Desktop / Cursor）

### Claude Code

仓库根目录已含 `.mcp.json`，在项目目录启动即自动加载 3 个 server：

```bash
cd mining-daily-mcp-agent
claude
# 进入后输入 /mcp 确认 server 已加载
```

> `.mcp.json` 使用本机绝对路径（`command`、`cwd`、`PYTHONPATH`、`DATA_DIR`）。换机器时请相应修改。

### Claude Desktop / Cursor

使用仓库根目录的 `mcp-config.json`（fixture 模式，相对路径 `DATA_DIR=data/fixtures`）：

```json
{
  "mcpServers": {
    "mining-news-mcp":  { "command": "python", "args": ["-m", "servers.mining_news_mcp.server"],  "env": { "DATA_DIR": "data/fixtures" } },
    "mineral-pdf-mcp":  { "command": "python", "args": ["-m", "servers.mineral_pdf_mcp.server"],  "env": { "DATA_DIR": "data/fixtures" } },
    "lme-price-mcp":    { "command": "python", "args": ["-m", "servers.lme_price_mcp.server"],    "env": { "DATA_DIR": "data/fixtures" } }
  }
}
```

> 若客户端启动目录不是仓库根目录，请把每个 server 的 `DATA_DIR` 改为 fixture 绝对路径，或把客户端工作目录设为仓库根。live 模式配置参考 `mcp-config.live.example.json`。

---

## 17. 环境变量参考总表

| 变量 | 作用域 | 默认 | 说明 |
| --- | --- | --- | --- |
| `AGENT_TRANSPORT` | CLI | `local` | `--transport` 默认值（`local`/`mcp`） |
| `DATA_DIR` | 全局 | `data/fixtures` | fixture 数据目录 |
| `RESOURCE_PDF_URL` | Agent/PDF | 项目映射/默认 fixture | 储量报告 URL（fixture / 本地 / 远程） |
| `LIVE_MODE` | 新闻/价格 | `false` | 真值时默认进 live |
| `NEWS_MODE` | 新闻 | 随 `LIVE_MODE` | `live` / `fixture` / `auto` |
| `NEWS_RSS_URLS` | 新闻 | `https://www.mining.com/feed/` | 逗号分隔的 RSS 列表 |
| `PRICE_MODE` | 价格 | 随 `LIVE_MODE` | `live` / `fixture` / `auto` |
| `PRICE_CSV_PATH` | 价格 | — | 手动授权 CSV 路径 |
| `PRICE_API_URL` | 价格 | — | 通用 JSON API（支持 `{commodity}/{date}/{days}`） |
| `HTTP_TIMEOUT_SECONDS` | HTTP | 新闻 12 / 价格 15 / PDF 20 | 抓取超时 |
| `HTTP_RETRIES` | HTTP | `2` | 重试次数 |
| `HTTP_USER_AGENT` | HTTP | 内置 UA | 自定义 User-Agent |
| `LLM_ENABLED` | LLM | `false` | 是否启用模型润色 |
| `OPENAI_API_KEY` | LLM | — | 模型 key（启用润色必需） |
| `OPENAI_BASE_URL` | LLM | `https://api.openai.com/v1` | OpenAI 兼容端点 |
| `OPENAI_MODEL` | LLM | `gpt-4o-mini` | 模型名 |
| `LLM_MAX_TOKENS` / `LLM_TEMPERATURE` / `LLM_TIMEOUT_SECONDS` | LLM | 1800 / 0.2 / 60 | 生成参数 |
| `ENV_FILE` | 加载器 | — | 指定 `.env` 路径（否则自动向上查找） |

> `.env` 由 `project_env.py:load_dotenv` 加载，**不会覆盖已存在的真实环境变量**；从当前工作目录逐级向上查找 `.env`，再回退仓库根。请只提交 `.env.example`，不要提交真实 `.env`（已在 `.gitignore`）。

---

## 18. 设计决策与 FAQ

- **为什么 fixture-first？** 评审/演示环境的稳定性 > 数据实时性。fixture 保证一条命令稳定出图，live 作为可插拔增强。
- **为什么自编排而非 LangGraph？** 题目重点是「MCP server + Agent 能真正跑通」，轻量自编排可控、易解释、调试风险低。
- **为什么 `local` 与 `mcp` 两条 transport？** `local` 让单测与离线演示零依赖；`mcp` 走真实 stdio 协议用于正式接入。二者复用同一 provider，保证行为一致。
- **价格源为何不内置 LME/SHFE 爬虫？** 这些源多需授权/登录且易因频控失效；项目选择接受授权后的 API/CSV，避免脆弱抓取。
- **LLM 失败会不会让报告崩？** 不会。`enhance_report` 任意异常/不完整输出都回退规则版并附注。
- **报告会污染仓库吗？** 不会。`reports/*.md` 已被忽略；示例输出单独放 `examples/`。

---

## 19. 题 #2 验收对照表

| 题面要求 | 本项目实现 |
| --- | --- |
| ≥3 个 MCP server | `mining-news-mcp` / `mineral-pdf-mcp` / `lme-price-mcp`，均 FastMCP stdio |
| 1 个 client 端 Agent | `agent/`（CLI + orchestrator + 工具客户端 + 渲染 + 可选 LLM） |
| 输入中文需求 | 「给我生成一份关于Pilbara锂矿的今日简报」 |
| 输出 Markdown 简报 | 新闻摘要 / 储量 / 价格走势 / 风险提示 / 引用源 5 段式 |
| 带引用源 | 新闻 `citations`、储量 `evidence`、价格 `source_url` |
| `mcp-config.json` 可接 Desktop/Cursor | 提供 `mcp-config.json` + `.mcp.json` + live 示例 |
| `RUN.md` 5 分钟跑通 | 提供，含一条 `docker compose` 命令 |
| 一条 docker 命令 | `docker compose up --build` |
| 离线可复现 | fixture-first，无外网/无 key 可跑 |
| 可测试 | 15 个 pytest 用例 |
| 不编造数据 | 结构化错误 + `needs_human_review` |

---

## 20. 已知边界与后续规划

- **PDF 表格抽取为规则版**：当前用正则匹配「分类 + 矿石量 + 品位 + 金属量」行；复杂多列表格/跨页表格建议接 PyMuPDF 表格识别或 LLM 结构化抽取（已预留 `needs_human_review` 兜底）。
- **新闻正文抽取为标准库实现**：`_ReadableHTMLParser` 覆盖常见结构，复杂 SPA/付费墙页面可接 readability/trafilatura 类库增强。
- **价格趋势为线性首尾对比**：可扩展为移动均线、波动率、分位数等指标。
- **意图解析为规则匹配**：项目/矿种/时间窗用正则与别名表；可扩展更多公司、矿种与多语言。
- **后续可加**：结果缓存与频控、更多 RSS/价格源 adapter、报告多语言输出、Web/API 服务化。

---

> 相关文档：[`RUN.md`](RUN.md)（5 分钟复现）· [`DATA_SOURCE_NOTES.md`](DATA_SOURCE_NOTES.md)（数据源接入）· [`MCP_MINING_DAILY_AGENT_PLAN.md`](MCP_MINING_DAILY_AGENT_PLAN.md)（选题与实施计划）· [`examples/pilbara_daily_report.md`](examples/pilbara_daily_report.md)（示例输出）
