FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY agent ./agent
COPY servers ./servers
COPY data ./data
COPY tests ./tests
COPY mcp-config.json RUN.md ./

RUN pip install --no-cache-dir -e ".[dev,live]"

ENV DATA_DIR=/app/data/fixtures
ENV AGENT_TRANSPORT=mcp

CMD ["python", "-m", "agent.cli", "--transport", "mcp", "给我生成一份关于Pilbara锂矿的今日简报"]
