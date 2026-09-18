# 开源仓库清单（Agent Infra 方向）

> 用法：**不要挨个 star 完就算学过。** 每个仓库标注了「怎么用」——是精读源码、是当作对照参照、还是拿来提 PR。四个月读透 3 个仓库，比浏览 30 个有用。

## 一、Agent 运行时与框架

| 仓库 | 怎么用 |
| --- | --- |
| [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk) | **精读**。项目一要暴露 MCP server 接口，这是必读代码。看 transport 抽象和 tool 注册机制 |
| [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | **对照**。手写完 mini-agent 后读它的状态机与 checkpoint 设计，写对比博客 |
| [All-Hands-AI/OpenHands](https://github.com/All-Hands-AI/OpenHands) | **精读运行时部分**。真实 code agent 的沙箱执行、事件流设计，和项目一直接对标 |
| [langgenius/dify](https://github.com/langgenius/dify) | **对照 + 提 PR**。看平台层怎么做多租户、工作流编排、模型路由。issue 对新人友好 |
| [browser-use/browser-use](https://github.com/browser-use/browser-use) | 快速浏览。看浏览器类工具怎么把 DOM 压进有限 context——context engineering 的典型案例 |

## 二、沙箱与隔离（项目一的直接参照）

| 仓库 / 项目 | 怎么用 |
| --- | --- |
| [e2b-dev/E2B](https://github.com/e2b-dev/E2B) | **重点对照**。商业级 agent 沙箱，看它的 API 设计、会话模型、冷启动方案。面试被问「和业界方案的差距」时靠它作答 |
| [google/gvisor](https://github.com/google/gvisor) | 读[文档](https://gvisor.dev/docs/)理解用户态内核如何拦截 syscall，不必读源码 |
| [firecracker-microvm/firecracker](https://github.com/firecracker-microvm/firecracker) | 读 README 与设计文档，理解 microVM 的隔离强度与启动开销 |
| [docker/docker-py](https://github.com/docker/docker-py) | **直接用**。项目一的容器编排靠它，顺手读一下 API 封装 |
| [containerd/containerd](https://github.com/containerd/containerd) | 选读。想深入容器生命周期管理时再看 |

## 三、推理引擎（项目二）

| 仓库 | 怎么用 |
| --- | --- |
| [vllm-project/vllm](https://github.com/vllm-project/vllm) | **精读调度与 KV cache 管理部分** + 提 PR。看 `core/scheduler` 和 block manager，这是 PagedAttention 的落地实现 |
| [sgl-project/sglang](https://github.com/sgl-project/sglang) | 对照 vLLM 看 RadixAttention 的差异。也是新人 PR 友好的仓库 |
| [huggingface/text-generation-inference](https://github.com/huggingface/text-generation-inference) | 选读。作为第三种设计思路参照 |
| [Dao-AILab/flash-attention](https://github.com/Dao-AILab/flash-attention) | 读 README + 论文，理解 IO 感知的 attention 优化。不用读 CUDA 源码 |
| [casper-hansen/AutoAWQ](https://github.com/casper-hansen/AutoAWQ) | **直接用**。做量化实验时用它，顺便看量化流程 |

## 四、评测与可观测性（差异化重点）

| 仓库 | 怎么用 |
| --- | --- |
| [SWE-bench/SWE-bench](https://github.com/SWE-bench/SWE-bench) | **精读评测框架设计**。项目二的 eval harness 直接参考它的任务定义、执行隔离、结果判定 |
| [langfuse/langfuse](https://github.com/langfuse/langfuse) | **直接用**。agent trace 与成本核算，比自己造轮子省时间。也可以自建对比 |
| [open-telemetry/opentelemetry-python](https://github.com/open-telemetry/opentelemetry-python) | **直接用**。项目一的埋点靠它，理解 span 层级怎么组织 agent 的多步调用 |
| [explodinggradients/ragas](https://github.com/explodinggradients/ragas) | 浏览。RAG 评估指标的标准实现，理解 faithfulness / context precision 怎么算 |
| [openai/evals](https://github.com/openai/evals) | 选读。看评测任务的抽象方式 |

## 五、训练与 RL infra（了解即可，不是主攻）

| 仓库 | 怎么用 |
| --- | --- |
| [volcengine/verl](https://github.com/volcengine/verl) | 浏览 README 与架构图。面试被问 agent RL 训练时能说出「rollout 与 training 分离」的基本盘 |
| [huggingface/trl](https://github.com/huggingface/trl) | 浏览。知道 SFT / DPO / PPO 的代码长什么样 |
| [ray-project/ray](https://github.com/ray-project/ray) | 浏览。分布式任务编排的事实标准，推理与训练 infra 里都会遇到 |

## 六、提 PR 的目标仓库排序

按「上手难度 × 与你项目的相关度」排：

1. **MCP python-sdk** —— 你项目一在用，踩到的坑就是最好的 PR 素材
2. **vLLM / SGLang** —— 文档、示例、测试补全类 issue 常年有，含金量高
3. **dify** —— 迭代快，`good first issue` 多
4. **Langfuse / docker-py** —— 体量小，维护者响应快

**流程**：先在 issue 里说明你要做什么，避免重复劳动 → 严格遵守 CONTRIBUTING 与 lint → PR 描述写清动机和验证方式。

## 七、维护约定

- 每读完一个仓库，在 `notes/` 下写一份笔记（模块划分 / 核心抽象 / 学到的设计 / 可以改进的地方）
- 在这里给读过的仓库标注状态：`[已读]` / `[在读]` / `[待读]`
- 链接失效或仓库改名时随手修掉
