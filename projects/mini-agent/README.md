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

### 上传并分析持仓 CSV

接口：

```text
POST /portfolio/analyze
Content-Type: multipart/form-data
```

上传示例：

```bash
curl -sS \
  -X POST \
  http://127.0.0.1:8001/portfolio/analyze \
  -F 'file=@data/portfolio.csv;type=text/csv'
```

上传限制：

- 文件名必须以 `.csv` 结尾；
- 文件大小不能超过 1 MiB；
- 文件必须使用 UTF-8 编码；
- CSV 必须包含 `name`、`asset_type`、`quantity`、`price`；
- `quantity` 和 `price` 必须是大于 0 的有限数字。

接口返回：

- `200`：分析成功；
- `413`：文件超过大小限制；
- `415`：不是 CSV 文件；
- `422`：编码错误或 CSV 内容不符合业务规则。

持仓市值使用 `Decimal` 计算，权重和 HHI 在完成高精度计算后，
使用 `ROUND_HALF_UP` 统一保留 4 位小数。


## 使用网页聊天界面

启动 HTTP API 后，在浏览器打开：

```text
http://127.0.0.1:8000/
```

点击“新对话”会调用 `DELETE /conversations/{conversation_id}` 清除服务端的内存历史，再生成新的 `conversation_id`。流式回答尚未结束时，该按钮会被禁用，避免旧请求写入新会话。

## 运行 MCP Server

使用 MCP Inspector 启动和调试：

```bash
uv run mcp dev src/mini_agent/mcp_server.py:mcp
```

当前 MCP Server 提供七个工具：

- `calculator`：计算数学表达式。
- `list_files`：列出 `data` 目录内可读取的文件路径。
- `read_file`：安全读取 `data` 目录中的文件。
- `analyze_portfolio`：分析包含 `name`、`asset_type`、`quantity`
  和 `price` 的持仓 CSV，返回总市值、持仓权重、最大持仓、
  资产配置比例与 HHI 集中度。金额计算使用 `Decimal`，
  避免金融计算中的浮点精度误差。
- `get_portfolio`：根据 `portfolio_id` 从 SQLite 中读取已经保存的
  持仓分析，使 Agent 不需要重复接收完整 CSV。
- `assess_portfolio_risk`：根据 `portfolio_id` 执行确定性风险规则，
  返回整体等级、风险信号、实际观测值、触发阈值和免责声明。
- `run_python`：在受限 Docker 容器中执行 Python。它支持通过
  `input_files` 接收文本文件，文件经过路径和大小校验后，以只读方式
  挂载到容器的 `/inputs`；代码产生的文件写入 `/workspace`。
  工具返回 `execution_id`、`status`、退出码、标准输出/错误预览、
  耗时和产物摘要。`status` 可以区分成功、代码错误、超时、
  输出超限和 Docker 基础设施错误。返回给模型的 stdout/stderr
  各截取前 2000 个字符，产物正文不会直接发送给模型。
  运行该工具需要 Docker Desktop。

`read_file` 不允许通过 `..` 读取 `data` 目录之外的文件。
目前 API 没有鉴权，只供本机开发和面试演示，不要直接暴露到公网。

## MCP 调用架构

mini-agent 不再直接调用本地工具函数，而是通过 MCP Client 动态发现并调用 MCP Server 中的工具：

```text
用户问题
  ↓
LLM 决定是否调用工具
  ↓
MCP Client
  ↓ stdio
MCP Server
  ↓
calculator / list_files / read_file / analyze_portfolio / get_portfolio / assess_portfolio_risk / run_python
```

`mcp_client.py` 负责：

- 通过 `stdio` 启动并连接 MCP Server。
- 动态获取工具名称、描述和参数 Schema。
- 将 MCP 工具转换成 LLM 接口需要的格式。
- 执行工具并把结果返回 Agent Loop。

运行 `uv run python main.py` 时，MCP Client 会自动启动 MCP Server 子进程，不需要提前手动启动服务器。

## 持仓分析

`analyze_portfolio` 接收 CSV 文本：

```csv
name,asset_type,quantity,price
股票基金,equity_fund,20,100
债券基金,bond_fund,20,50
现金,cash,1000,1
```

当前功能只分析用户提供的数据，不连接交易账户，也不生成个性化投资建议。

### 查询持仓分析

上传成功后会返回 `portfolio_id`、文件指纹、创建时间和结构化分析结果。原始 CSV 不会写入数据库。

```text
GET /portfolio/{portfolio_id}
```

### 查询持仓风险

```text
GET /portfolio/{portfolio_id}/risk
```

风险接口从 SQLite 读取持仓分析，再执行确定性规则。当前演示规则包括：

- 最大单一持仓达到 `0.3000` 触发中等级信号，达到 `0.5000` 触发高等级信号；
- HHI 达到 `0.2500` 触发中等级信号，达到 `0.3500` 触发高等级信号；
- 权益类资产占比达到 `0.6000` 触发中等级信号，达到 `0.8000` 触发高等级信号；
- 现金类资产占比达到 `0.5000` 触发中等级信号。

整体等级取所有信号中的最高等级。所有阈值都是项目演示用的可配置规则，不构成投资建议。

## 持仓持久化

持仓分析使用 SQLite 保存，默认数据库位置为：

```text
data/portfolios.sqlite3
```

也可以通过环境变量修改：

```text
PORTFOLIO_DATABASE_PATH=/path/to/portfolios.sqlite3
```

数据流如下：

```text
用户上传 CSV
  ↓
FastAPI 校验文件类型、大小和编码
  ↓
PortfolioAnalyzer 使用 Decimal 计算分析指标
  ↓
PortfolioRepository 生成 portfolio_id 和 SHA-256 指纹
  ↓
SQLite 只保存元数据与分析 JSON，不保存原始 CSV
  ↓
MCP get_portfolio 根据 portfolio_id 查询分析结果
  ↓
PortfolioRiskEngine 执行确定性风险规则
  ↓
API 或 MCP 返回可审计的风险报告
```

API 主进程和 MCP 子进程各自拥有独立的 `PortfolioRepository` 对象，但它们连接同一个 SQLite 文件，因此可以跨进程共享持仓分析记录。

启动 MCP 子进程时只通过环境变量白名单传递数据库路径，不会把主进程的全部环境变量和 API Key 交给工具进程。



## 运行测试

运行不依赖 Docker 的常规测试：

```bash
uv run pytest -q
```
运行真实的 MCP → Docker 端到端测试：
```bash
RUN_DOCKER_TESTS=1 uv run pytest -q tests/test_mcp_client.py::test_run_python_with_docker
```
这里将两类测试分开，是为了让日常测试快速稳定，同时保留真实 Docker 链路的验收能力。