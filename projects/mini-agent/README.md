# Mini Agent

一个用 Python 实现的轻量 AI Agent，支持流式输出、工具调用、上下文管理、失败重试、HTTP API 和 MCP Server。

## 安装依赖

```bash
uv sync
```

## 配置环境变量

复制示例配置：

```bash
cp .env.example .env
```

然后在 `.env` 中填写 API Key：

```text
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://apihub.agnes-ai.com/v1
LLM_MODEL=agnes-2.5-flash
```

如果需要通过 Clash 访问 API，可以保留代理配置：

```text
HTTPS_PROXY=http://127.0.0.1:7897
HTTP_PROXY=http://127.0.0.1:7897
```

## 运行命令行 Agent

```bash
uv run python main.py
```

## 运行 HTTP API

```bash
uv run uvicorn mini_agent.api:app --reload
```

健康检查地址：

```text
http://127.0.0.1:8000/health
```

## 运行 MCP Server

使用 MCP Inspector 启动和调试：

```bash
uv run mcp dev src/mini_agent/mcp_server.py:mcp
```

当前 MCP Server 提供两个工具：

- `calculator`：计算数学表达式。
- `read_file`：安全读取 `data` 目录中的文件。

`read_file` 不允许通过 `..` 读取 `data` 目录之外的文件。

## 运行测试

```bash
uv run pytest -q
```