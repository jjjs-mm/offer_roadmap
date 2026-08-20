# 论文与博客清单（Agent Infra 方向）

> 用法：**读透 20 篇远胜浏览 200 篇。** 标 ★ 的必读，读完在 `blog/` 写一篇自己的复述与批判——能写出来才算读懂。
> 记录格式：读完把标题前的 `[ ]` 改成 `[x]`，并附上你的笔记链接。

## 一、必读工程博客（优先级最高）

这些比论文更贴近面试和实际工作。

- [ ] ★ [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) — Anthropic
  工业界对 agent 与 workflow 边界最清晰的论述。**面试高频，务必能复述其中的五种模式和适用场景。**
- [ ] ★ Anthropic 工程博客的 context engineering 与 agent 工具设计系列 — [anthropic.com/engineering](https://www.anthropic.com/engineering)
  context 怎么组织、工具怎么写描述、多 agent 怎么分工，都是直接可用的经验。
- [ ] ★ [Agents](https://huyenchip.com/2025/01/07/agents.html) — Chip Huyen
  系统性梳理 agent 的规划、工具、失败模式，结构比大多数论文清楚。
- [ ] [LLM Powered Autonomous Agents](https://lilianweng.github.io/posts/2023-06-23-agent/) — Lilian Weng
  agent 组件划分的经典入门，读它建立词汇表。
- [ ] [Extrinsic Hallucinations in LLMs](https://lilianweng.github.io/posts/2024-07-07-hallucination/) — Lilian Weng
  幻觉成因与缓解手段，面试必问题的答案来源。
- [ ] ★ [vLLM 官方博客与文档](https://blog.vllm.ai/) / [docs.vllm.ai](https://docs.vllm.ai/)
  continuous batching、prefix caching、chunked prefill 的第一手解释。
- [ ] [SGLang 博客](https://lmsys.org/blog/) — LMSYS
  RadixAttention 与调度优化，和 vLLM 对照读。
- [ ] ★ [Model Context Protocol 规范](https://modelcontextprotocol.io/)
  项目一要实现 MCP server，规范必须读原文，尤其 transport 与 tool 定义部分。

## 二、Agent 论文

- [ ] ★ [ReAct: Synergizing Reasoning and Acting](https://arxiv.org/abs/2210.03629)
  agent 范式的起点。**必读，面试直接问。**
- [ ] [Toolformer](https://arxiv.org/abs/2302.04761) — 模型如何学会调工具
- [ ] [Reflexion](https://arxiv.org/abs/2303.11366) — 反思机制，agent 自我纠错的代表工作
- [ ] [Tree of Thoughts](https://arxiv.org/abs/2305.10601) — 搜索式推理，理解 planning 的代价
- [ ] ★ [SWE-bench](https://arxiv.org/abs/2310.06770) — 真实软件工程任务评测基准，项目二的评测集来源
- [ ] [SWE-agent](https://arxiv.org/abs/2405.15793) — agent-computer interface 的设计，**和你的沙箱项目直接相关**
- [ ] [Gorilla](https://arxiv.org/abs/2305.15334) — 大规模 API 调用，工具太多时怎么选
- [ ] ★ [Lost in the Middle](https://arxiv.org/abs/2307.03172) — 长上下文的信息利用缺陷，context engineering 的理论依据
- [ ] [Generative Agents](https://arxiv.org/abs/2304.03442) — 记忆与反思系统的设计，看 memory 分层思路
- [ ] [Not what you've signed up for](https://arxiv.org/abs/2302.12173) — 间接 prompt injection，agent 安全必读

## 三、推理与系统论文

- [ ] ★ [Efficient Memory Management for LLM Serving with PagedAttention](https://arxiv.org/abs/2309.06180)
  vLLM 的原始论文。**KV cache 分页管理，面试白板题。**
- [ ] ★ Orca: A Distributed Serving System for Transformer-Based Generative Models（OSDI '22）
  continuous batching（iteration-level scheduling）的原始工作，搜 OSDI 2022 proceedings 可下载。
- [ ] [FlashAttention](https://arxiv.org/abs/2205.14135) — IO 感知的 attention，理解显存带宽为何是瓶颈
- [ ] [AWQ](https://arxiv.org/abs/2306.00978) 与 [GPTQ](https://arxiv.org/abs/2210.17323) — 两种量化路线，项目二的实验依据
- [ ] [Speculative Decoding](https://arxiv.org/abs/2211.17192) — 投机解码的原理与收益条件
- [ ] [SARATHI](https://arxiv.org/abs/2308.16369) — chunked prefill，理解 prefill/decode 调度冲突
- [ ] [Firecracker: Lightweight Virtualization for Serverless](https://www.usenix.org/conference/nsdi20/presentation/agache)（NSDI '20）
  microVM 的隔离与冷启动权衡，**沙箱项目的核心参照**
- [ ] [gVisor 设计文档](https://gvisor.dev/docs/architecture_guide/) — 用户态内核如何拦截 syscall

## 四、模型基础论文（补基本功，选读）

- [ ] ★ [Attention Is All You Need](https://arxiv.org/abs/1706.03762)
- [ ] [RoFormer / RoPE](https://arxiv.org/abs/2104.09864) — 旋转位置编码，长度外推的基础
- [ ] [GQA](https://arxiv.org/abs/2305.13245) — 为什么现在主流模型都用它省 KV cache
- [ ] [Chain-of-Thought](https://arxiv.org/abs/2201.11903)
- [ ] [DPO](https://arxiv.org/abs/2305.18290) — 对齐方法，了解即可
- [ ] [Switch Transformer](https://arxiv.org/abs/2101.03961) — MoE 路由机制
- [ ] [Judging LLM-as-a-Judge / MT-Bench](https://arxiv.org/abs/2306.05685) — eval harness 里的自动归因要用

## 五、阅读节奏

对照 [roadmap.md](../docs/roadmap.md)：

| 月份 | 读什么 |
| --- | --- |
| 第 1 月 | 第一节工程博客全部 + ReAct + Lost in the Middle + MCP 规范 |
| 第 2 月 | Firecracker + gVisor 文档 + SWE-agent（配合沙箱项目） |
| 第 3 月 | PagedAttention + Orca + AWQ/GPTQ + SWE-bench + LLM-as-Judge |
| 第 4 月 | 第四节基础论文补齐（面试八股的底层依据） |

## 六、读论文的方法

**不要从第一页读到最后一页。** 顺序是：

1. 摘要 + 图表 —— 先搞清它解决什么问题、结果多好
2. Introduction 最后一段 —— 通常是贡献列表
3. 方法部分的核心机制 —— 只读到能自己画出来为止
4. 实验部分挑一张关键表 —— 看它和谁比、赢在哪
5. 局限性与相关工作 —— **面试里能说出一篇论文的局限，比背下它的方法更值钱**

读完写笔记必答三个问题：**它解决什么问题？关键洞察是什么？如果让我实现，最难的地方在哪？**

## 七、维护约定

- 链接可能失效或迁移，随手修掉；不确定的博客用「站点 + 标题」记录，不要编造 URL
- 自己写的博客链接追加到对应条目后面，形成「读过 → 写过」的闭环
