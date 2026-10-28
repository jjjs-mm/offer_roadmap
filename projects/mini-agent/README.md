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
## 基金知识文档

系统支持上传 UTF-8 编码的 TXT、Markdown，以及带文本层的 PDF，作为 RAG 检索的数据来源。PDF 按页解析，每个知识块保留原始页码。

### 上传知识文档

```text
POST /knowledge/documents
Content-Type: multipart/form-data
```

示例：

```bash
curl -sS \
  -X POST \
  http://127.0.0.1:8000/knowledge/documents \
  -F 'file=@fund_product_summary.pdf;type=application/pdf' \
  -F 'source_url=https://fund.example/fund_product_summary.pdf' \
  -F 'published_at=2026-05-29'
```

上传限制：

- 文件名必须以 `.txt`、`.md` 或 `.pdf` 结尾；
- 文件大小不能超过 10 MiB；
- TXT 与 Markdown 必须使用 UTF-8 编码；PDF 必须包含可提取的文本层；
- 文档内容不能为空。

上传成功返回 `201`，响应包含：

- `document_id`：知识文档的唯一标识；
- `content_sha256`：原始文件的 SHA-256 指纹；
- `created_at`：文档创建时间；
- `source_url`：可选的公开原文地址；
- `published_at`：可选的原文发布日期；
- `chunk_count`：知识块数量；
- `chunks`：切分后的知识块及其引用元数据。

### 异步导入任务

对于较大的 PDF 或批量导入，推荐使用异步入口：

```text
POST /knowledge/ingestions
Content-Type: multipart/form-data
```

接口完成文件大小与元数据校验后立即返回 `202` 和 `ingestion_id`；后台再执行 PDF 解析、文本切分、向量化和数据库写入。通过以下接口轮询状态：

```text
GET /knowledge/ingestions/{ingestion_id}
```

任务状态为 `queued → running → succeeded / failed`。失败任务可显式重试：

```text
POST /knowledge/ingestions/{ingestion_id}/retry
```

每份上传原文件按 SHA-256 去重：相同内容重复提交会复用同一条任务，避免重复解析与重复向量化。任务记录持久化保存原文件、重试次数、阶段状态、失败摘要和最终 `document_id`；只有任务成功后，文档才会出现在知识库检索结果中。

当前实现采用 FastAPI 进程内后台执行器，适合单机部署与演示；任务状态和原文件仍持久化在 SQLite。多实例生产部署时可将同一状态机接入 Redis/Kafka 与独立 Worker，避免 API 进程重启后等待中的任务无法自动续跑。

### 查询知识文档

```text
GET /knowledge/documents/{document_id}
```

记录不存在时返回 `404`。

### 文档切分

当前使用固定字符窗口作为第一版可重复基线：

```text
chunk_size = 500
overlap = 50
```

`overlap` 会让相邻文本块保留一段重复内容，降低答案所需信息恰好跨越切分边界时的丢失风险。

每个知识块保存：

- `document_id`；
- `source_name`；
- `chunk_index`；
- `page_number`：PDF 原始页码，文本文件为 `null`；
- `content`。

后续可以将固定窗口与段落切分、递归切分等方案进行召回效果对比。

### 知识库持久化

知识文档使用 SQLite 保存，默认数据库位置为：

```text
data/knowledge.sqlite3
```

可以通过环境变量修改：

```text
KNOWLEDGE_DATABASE_PATH=/path/to/knowledge.sqlite3
```

异步任务使用独立数据库，便于将任务生命周期与已入库知识分离：

```text
data/ingestions.sqlite3
```

```ini
INGESTION_DATABASE_PATH=/path/to/ingestions.sqlite3
```

数据流如下：

```text
用户上传 TXT、Markdown 或 PDF
  ↓
FastAPI 校验扩展名、大小、编码或 PDF 文本层
  ↓
PDF 逐页抽取，chunk_document 使用固定窗口和重叠区域切分
  ↓
KnowledgeRepository 生成 document_id 和 SHA-256 指纹
  ↓
knowledge_documents 保存文档元数据
  ↓
knowledge_chunks 保存文本块与引用信息
  ↓
GET 接口根据 document_id 读取完整记录
```

`knowledge_documents` 与 `knowledge_chunks` 是一对多关系。文档元数据和全部知识块在同一个 SQLite 事务中写入，避免只保存部分知识块。

### 真实公开基金资料

`data/public_funds/manifest.json` 固化了 24 份基金管理人官网资料，来自华夏、平安、易方达、博时、富国、嘉实、汇添富、广发和招商，覆盖股票指数、行业 ETF、混合、纯债、二级债、中短债、货币、QDII 指数联接、全球配置、原油主题 QDII-FOF、红利混合、指数增强和海外股票等 18 个产品类型。清单保存基金代码、基金公司、资产类型、发布日期、原始 URL 与 SHA-256，下载后会先校验文件指纹再导入。原始 PDF 位于忽略目录，不直接提交进 Git。

```bash
uv run python scripts/import_public_funds.py
```

导入脚本具有幂等性：同一 SHA-256 已存在时复用原记录，不重复写入。所有文件均通过 PDF 签名、哈希和文本可提取性检查；24 份资料均可按页切分并生成引用。新增的广发、招商资料均已按“每份 3 条可回答题 + 1 条拒答题”完成开发集标注并纳入回归指标。

语料扩展后可运行审计脚本，校验全部原始文件哈希并输出基金公司、产品类型和发布日期覆盖度：

```bash
uv run python scripts/audit_public_fund_corpus.py
```

新增资料和标注必须遵循 [公开基金 PDF 标注规范](data/public_fund_annotation_guidelines.md)：开发集、冻结测试和盲测严格隔离，盲测首次运行后不再修改。

回答引用现在可以定位到“文件名 + PDF 页码 + 知识块编号”。这使面试演示中的投资目标、费率和风险结论都能回到基金公司发布的原始法律文件核验。

### 真实 PDF 检索评测

真实资料评测分为两部分：

- `data/public_fund_eval_dev.json`：130 条开发用例，其中 98 条可回答、32 条应拒答；包含从盲测失败类型抽象出的开发样本，但不复用盲测原句；
- `data/public_fund_eval_test.json`：30 条冻结测试用例，其中 20 条可回答、10 条应拒答，使用不同的自然语言问法。
- `data/public_fund_eval_blind_v2.json`：在 `QueryNormalizer v1` 实现后新增的 30 条盲测用例，其中 20 条可回答、10 条应拒答；首次运行后冻结，不参与后续规则调优；
- `data/public_fund_eval_blind_v3.json`：来自新增、未参与前述开发的嘉实官方 PDF 的 10 条外部来源盲测，其中 5 条可回答、5 条应拒答；首次运行后冻结，不参与后续规则调优。

问题覆盖投资目标、投资范围、策略、费用、风险、基金经理、时间冲突、评级、私人联系方式与环境指标。评测明确拆分两个阶段：

1. `catalog`：从全部 PDF 中找到正确来源；
2. `selected_document`：用户选定基金后，在单份 PDF 内找到正确页码。

```bash
uv run python scripts/evaluate_public_funds.py \
  --output reports/public_fund_retrieval_dev_report.json

uv run python scripts/evaluate_public_funds.py \
  --include-semantic \
  --minimum-vector-score 0.40 \
  --output reports/public_fund_retrieval_semantic_dev_normalized_report.json

uv run python scripts/evaluate_public_funds.py \
  --dataset data/public_fund_eval_test.json \
  --include-semantic \
  --minimum-vector-score 0.40 \
  --output reports/public_fund_retrieval_semantic_test_normalized_report.json

uv run python scripts/evaluate_public_funds.py \
  --dataset data/public_fund_eval_blind_v2.json \
  --include-semantic \
  --minimum-vector-score 0.40 \
  --output reports/public_fund_retrieval_blind_v2_report.json

uv run python scripts/evaluate_public_funds.py \
  --dataset data/public_fund_eval_blind_v3.json \
  --include-semantic \
  --minimum-vector-score 0.40 \
  --output reports/public_fund_retrieval_blind_v3_report.json
```

当前开发集结果：

- ngram 全库来源 `Hit@1/Hit@3 = 96.6%/100%`；
- ngram 选定文档 `Page Hit@1/Hit@3 = 94.9%/98.3%`；
- 阈值 `0.40` 的混合检索选定文档 `Page Hit@1/Hit@3 = 94.9%/100%`。

自然问法优化后的回归结果：

- 混合检索全库来源 `Hit@1/Hit@3 = 95%/100%`；
- 混合检索选定文档 `Page Hit@1/Hit@3 = 95%/100%`；
- 测试题目与标准页码保持不变，报告额外输出 `answerable_rejected_case_ids`、`unanswerable_accepted_case_ids` 和 `page_miss_case_ids` 以定位回归失败样本。

这组结果说明检索相关性与证据充分性是两个不同问题：相关段落可以被召回，但不一定包含问题所需的明确事实。因此项目保留高召回检索，并把“是否足以回答”作为下一层单独评测，而不是用一个相似度阈值同时解决两件事。当前 200 条用例仍属于工程回归数据，不能当作生产准确率。

### 关键词检索基线

`GET /knowledge/search?q=管理费&limit=5` 对知识块内容做原样子串匹配，返回匹配内容及 `document_id`、`source_name`、`chunk_index`，便于后续追溯来源。

使用虚构的 `data/fund_research_demo.md` 验收：查询“管理费”能命中 1 个知识块；查询“这只基金每年收多少费用？”返回空列表。

### 字符二元组检索与评测

`GET /knowledge/search` 支持两种检索模式：

- `mode=keyword`：查询字符串必须原样出现在知识块中；
- `mode=ngram`：把查询和知识块规范化后拆成字符二元组，根据共同二元组数量进行排序。

`ngram` 是不依赖外部模型的词法检索基线，不是语义检索。

为了降低“基金”等公共词造成的误召回，检索器使用动态最低重叠阈值：

- 只有 1～2 个二元组的短查询，最低重叠分数为 1；
- 更长的查询，最低重叠分数为 2。

例如，“T+1”虽然只有一个二元组，但仍可正常召回；“基金经理是谁？”不会再因为资料中碰巧出现“基金”而被判断为有答案。

### 检索评测

评测数据分为三层：

```text
data/retrieval_eval_dataset.json   # 12 条 smoke 回归
data/retrieval_eval_dev.json       # 40 条开发集
data/retrieval_eval_test.json      # 24 条冻结测试集
```

三套数据共包含 76 条问题。开发集和测试集共享 12 份虚构基金资料，问题 ID 互不重复：

- `smoke` 用于快速功能回归；
- `dev` 用于失败分析和阈值调整；
- `test` 在检索方案冻结后只运行一次，用于验证泛化效果；
- 问题覆盖精确匹配、同义改写、相似文档干扰、短查询和无答案困难负例。

运行评测：

```bash
uv run python scripts/evaluate_retrieval.py

uv run python scripts/evaluate_retrieval.py \
  --dataset data/retrieval_eval_dev.json

uv run python scripts/evaluate_retrieval.py \
  --dataset data/retrieval_eval_test.json
```

评测指标包括：

- `Hit@1`：排名第一的文档是否正确；
- `Hit@K`：前 K 个文档中是否包含正确文档；
- `MRR`：正确文档出现位置的倒数排名均值；
- `rejection_rate`：无答案问题没有召回任何文档的比例；该指标只衡量空召回，不等同于最终答案拒答率；
- `p50/p95`：本机单次检索延迟分位数。

冻结方案在 24 条独立测试问题上的结果：

- `keyword`：Hit@1 `33.3%`、Hit@3 `33.3%`、MRR `33.3%`、空召回率 `100%`；
- `ngram`：Hit@1 `94.4%`、Hit@3 `94.4%`、MRR `94.4%`、空召回率 `66.7%`；
- 本机 `ngram` 检索延迟 p95 约为 `0.176 ms`。

完整机器可读报告保存在：

```text
reports/retrieval_eval_report.json       # smoke
reports/retrieval_eval_dev_report.json   # dev
reports/retrieval_eval_test_report.json  # test
```

### 本地向量与混合检索实验

项目使用 FastEmbed 和本地 `BAAI/bge-small-zh-v1.5` 模型实现向量检索，文档内容不需发送给第三方 Embedding API。`hybrid` 模式使用 RRF（Reciprocal Rank Fusion）合并 ngram 与向量排名，避免直接相加两种量纲不同的分数。

API 支持四种模式：

```text
keyword / ngram / vector / hybrid
```

首次使用 `vector` 或 `hybrid` 时会下载约 90 MB 的本地模型。查询和文档向量会在进程内缓存，避免重复推理。

使用开发集扫描语义相似度阈值：

```bash
uv run python scripts/tune_semantic_threshold.py
```

使用冻结测试集对比四种方案：

```bash
uv run python scripts/evaluate_retrieval.py \
  --dataset data/retrieval_eval_test.json \
  --include-semantic \
  --minimum-vector-score 0.65 \
  --output reports/retrieval_eval_semantic_test_report.json
```

在 24 条冻结测试问题上：

- `ngram`：Hit@1 `94.4%`、Hit@3 `94.4%`、MRR `94.4%`、空召回率 `66.7%`、p95 约 `0.176 ms`；
- `hybrid`：Hit@1 `88.9%`、Hit@3 `94.4%`、MRR `91.7%`、空召回率 `66.7%`、p95 约 `0.546 ms`。

该实验中，混合检索没有提高虚构冻结集的 Hit@3，反而降低 Hit@1 并增加延迟；但在真实 PDF 开发集上，阈值 `0.40` 的混合检索将选定文档 Page Hit@3 从 `93.3%` 提升到 `100%`。因此当前选定文档的 RAG 路径使用混合检索，并在未配置向量模型时回退到 ngram。全库搜索接口仍允许显式选择四种模式。

完整对比报告位于：

```text
reports/retrieval_eval_semantic_test_report.json
```

开发集用于识别错误类型，测试集不参与阈值调整。独立测试集中，`ngram` 未能识别“追加购买”和“追加申购”的同义关系；对于基金经理变更和具体股票持仓问题，它能召回主题相关文档，但文档并不包含问题所需事实。

这说明检索相关性和答案证据充分性必须分层评估。现有冻结评测集仍以人工构造语料为主，不能直接代表真实基金业务准确率；新增的官网 PDF 用于端到端演示和后续扩充真实评测集。`ngram` 仍会把全部知识块读取到 Python 中排序，数据量继续增长时需要迁移到专用索引，并继续评估答案忠实度和拒答能力。

### 基于证据的流式回答

用户选择知识文档后，系统执行以下流程：

1. 从所选文档中检索相关知识块；
2. 没有证据时直接拒答，不调用模型；
3. `EvidenceSufficiencyGate` 检查证据是否包含问题要求的明确事实；
4. 证据不足时返回结构化 `evidence_check` 事件并停止模型调用；
5. 证据充分时构造只能依据资料回答的 Grounded Prompt；
6. RAG 请求关闭 MCP 工具，避免无关工具调用与额外子进程开销；
7. 通过 SSE 流式返回模型答案；
8. 答案结束后返回文档 ID、文件名、PDF 页码和知识块序号作为引用。
9. 全链路将请求状态、阶段耗时和拒答原因写入可查询的 RAG Trace。

普通 Agent 对话仍然启用 MCP 工具。RAG 与工具 Agent 使用不同的能力路由，但复用同一套流式生成核心。

### 证据充分性判定

`EvidenceSufficiencyGate` 是检索器与生成模型之间的独立安全层。它不生成答案，只输出：

- `sufficient`：是否允许模型回答；
- `question_type`：费用、目标、范围、风险、业绩等问题类型；
- `reason_code`：可审计的通过或拒绝原因；
- `matched_chunk_indices`：参与判断的知识块。
- `required_evidence_fields`：本类问题允许回答所需的字段，例如“标的指数”“公开联系方式”或“赎回费”。

当前规则包括：费用必须存在明确费率或“不收取”表述；问题指定的年份必须出现在证据中；评级、私人联系方式和碳排放等问题必须存在对应字段；未知问题类型默认拒绝，而不是让模型猜测。

在进入检索器和判定层前，`QueryNormalizer` 会为少量、可解释的基金自然问法补充领域别名，例如“能买股票吗”补充“投资范围、是否投资、股票”，“复制哪条指数”补充“标的指数、跟踪指数”。原问题不会被改写，最终 Grounded Prompt 仍保留用户原文；未命中规则的问题也不会扩写。费用问题则优先在用户选定文档的完整费率表中确定答案，再进入通用 RAG 路径。

在 130 条真实 PDF 开发集 v6 上：

- ngram + 判定层：判定准确率 `90.8%`，可回答通过率 `87.8%`，越界拒答率 `100%`，错误放行率 `0%`；
- hybrid + 判定层：判定准确率 `90.8%`，可回答通过率 `87.8%`，越界拒答率 `100%`，错误放行率 `0%`。

30 条冻结测试的首次基线中，混合检索已达到 `Page Hit@3 = 100%`，但判定层可回答通过率只有 `35%`；10 条应拒答问题全部拒绝，错误放行率为 `0%`。该基线暴露出“能买股票吗”“复制哪条指数”等自然问法映射缺口。随后新增了独立、规则可审计的 `QueryNormalizer`，没有改动测试题目或标准页码；同一回归集复测后，混合检索门控准确率为 `100%`，可回答通过率为 `100%`，10 条应拒答问题仍全部拒绝，错误放行率为 `0%`。由于该回归集已参与问题诊断，它现在应被视为 v1 回归集而非完全独立的最终盲测；下一轮需要新增未见过的盲测集验证泛化。

新增的 30 条 `blind_v2` 在 `QueryNormalizer v1` 完成后才编写，并在首次评测后冻结：混合检索选定文档 `Page Hit@1/Hit@3 = 85%/100%`，但证据门控准确率仅 `46.7%`，可回答通过率 `30%`，应拒答拦截率 `80%`，错误放行率 `20%`。因此当前结论是：检索覆盖足够，但规则门控对未见自然问法仍有明显表述依赖，不能用于生产承诺。该报告保留失败 case ID，下一轮应从盲测暴露的失败类型抽象出开发集样本，再创建新的 `blind_v3` 验证，而不是直接对 `blind_v2` 过拟合。

`blind_v3` 使用新引入的嘉实原油 QDII-LOF 官方产品资料，文档来源、公司与字段表述均未参与前述开发。首次冻结运行中，混合检索选定文档 `Page Hit@1/Hit@3 = 60%/100%`；证据门控准确率 `80%`，可回答通过率 `60%`，5 条应拒答问题全部拦截，错误放行率 `0%`。两个被拒的可回答问题是“投资目标”和“投资策略”：证据页已被召回，但门控规则未把该基金的表述识别为足够直接的字段。这验证了跨机构检索覆盖尚可，但字段级证据规则仍需要以新的开发样本和新的盲测轮次迭代；本轮不会修改 `blind_v3` 或以其结果宣称泛化能力。

这些数字只用于回归和方案比较，不代表生产环境准确率。后续仍需继续扩大基金公司与文档格式覆盖，并增加跨页表格、扫描件和多版本冲突资料。

### 可审计 RAG Trace

每次 `/chat/stream` 请求开始时，服务会先返回一个 `trace` SSE 事件：

```json
{
  "type": "trace",
  "trace_id": "32 位请求标识"
}
```

系统使用 SQLite 持久化请求状态、检索方式、召回块数量、证据是否充分、拒答原因码、检索耗时、生成耗时、总耗时和错误摘要。Trace 不保存完整 Grounded Prompt、模型答案或 API Key，避免为可观测性额外复制敏感内容。

查询单次执行记录：

```text
GET /traces/{trace_id}
```

查询最近一段时间的运行汇总，用于接入面板或告警，而无需读取用户问题和模型答案：

```text
GET /traces/metrics?window_hours=24
```

返回请求总量、完成量、执行中的请求数、成功/业务拒答/失败数量，以及总时延 `p50`、`p95`。其中“拒答”是证据不足时的预期安全行为，不与基础设施或模型调用失败混为一类；指标聚合仅基于 Trace 元数据，不额外保存 Prompt、回答或密钥。

默认数据库位置为 `data/rag_traces.sqlite3`，可通过环境变量覆盖：

```ini
RAG_TRACE_DATABASE_PATH=/path/to/rag_traces.sqlite3
```

Trace 状态分为：

- `started`：请求已接收但尚未结束；
- `succeeded`：模型回答或确定性费用提取成功；
- `rejected`：无相关证据或证据充分性判定未通过；
- `failed`：文档不存在、模型流式生成失败等执行错误。

这种设计将“业务拒答”和“系统故障”分开：前者是安全策略按预期生效，后者才需要排查服务或模型依赖。Trace 写入失败只记录服务日志，不会中断主回答链路。

### 端到端答案评测

检索指标只能说明系统是否找到了相关文档，不能证明最终答案没有幻觉。因此项目额外提供端到端答案评测，覆盖 12 条 smoke 用例：

- 8 条可回答问题，包含精确查询和同义改写；
- 4 条资料中没有答案的问题，用于测试拒答；
- 每条可回答用例都声明必须出现的关键事实和标准引用来源。

评测集位于：

```text
data/answer_eval_dataset.json
```

先启动 API，再运行：

```bash
uv run python scripts/evaluate_answers.py \
  --base-url http://127.0.0.1:8003 \
  > reports/answer_eval_report.json
```

脚本会自动上传评测文档，逐题请求 `/chat/stream`，并从 SSE 事件中合并模型文本和引用来源。输出包含：

- `answer_correct_rate`：可回答题包含标准事实，无答案题确实拒答的比例；
- `citation_correct_rate`：引用来源与标准来源完全一致的比例；
- `abstention_accuracy`：系统的回答或拒答决策正确的比例；
- `overall_success_rate`：事实、引用和拒答决策同时正确的比例；
- `failed_case_ids`：未通过的用例 ID，用于快速定位失败类型。

答案中的百分号会统一中英文形式，并忽略空白差异。拒答通过“无法回答”“未提供”“资料不足”等显式表达识别。这套规则评测适合稳定回归和失败归因，但不能完全替代人工对答案语义和金融表述质量的审核。

首次真实端到端运行结果为：

- 答案正确率 `91.7%`；
- 引用正确率 `91.7%`；
- 拒答准确率 `91.7%`；
- 整体成功率 `91.7%`。

评测过程先发现“托管费”与“托管服务费”导致的规则误判，因此将标准事实改为支持多个等价表达，避免把评测器缺陷误当成模型错误。修正后只剩一条失败：字符 ngram 检索无法将“复制市场表现”与文档中的“跟踪宽基股票指数”建立语义联系。该失败为后续引入向量或混合检索提供了明确基线。

完整运行输出保存在：

```text
reports/answer_eval_report.json
```
