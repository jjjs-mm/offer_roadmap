# 常用站点与工具

## 一、投递与招聘信息

| 站点 | 用途 | 提醒 |
| --- | --- | --- |
| 各公司招聘官网 | 寒假实习 / 日常实习正式入口 | 大厂的实习岗位常年滚动更新，**每周固定刷一次** |
| [牛客网](https://www.nowcoder.com/) | 招聘信息汇总、面经、内推贴 | 面经看趋势就好，不要陷进焦虑帖 |
| BOSS 直聘 | 创业公司和小团队的主要渠道 | agent 方向创业公司多在这里发帖，活硬核、进得快 |
| [实习僧](https://www.shixiseng.com/) | 实习岗位聚合 | 补充渠道 |
| 微信内推群 / 实验室师兄师姐 | **转化率最高的渠道** | 内推优先级永远高于官网投递；学历权重主要作用在初筛这一关 |
| GitHub / 技术社区里的团队成员 | 冷启动内推 | 先提有价值的 PR 或提问，再谈内推，顺序别反 |

### 南京本地与远程渠道（阶段一日常实习专用）

| 渠道 | 用途 |
| --- | --- |
| 南京本地 AI 公司官网 / 公众号 | 本地做 LLM 应用与 Agent 平台的公司，规模小但活可能更硬核 |
| 江苏省 / 南京市工信局的备案大模型名单 | 公开信息里能挖出本地在做大模型的企业名单，是找本地岗位的冷门入口 |
| 运营商 / 电力 / 金融的科技子公司 | 南京行业大模型落地的主要去处，稳定但要问清技术含量 |
| 大厂在南京、苏州的研发中心 | 平台 / 云原生 / 后端岗为主，agent 核心团队通常不在这里 |
| **远程实习**（创业公司、开源项目商业化团队） | **被严重低估**。在南京拿到真 agent 经历的最优路径，很多团队接受远程或每周固定几天 |
| 苏州 / 上海（高铁 1–1.5h） | 能接受周中在当地住的话，选择面扩大一个量级 |

**避坑三问**（面试时一定要问）：我的 mentor 是谁？我写的代码进不进主干？团队有没有 GPU 和真实流量？三个都含糊的别去。另外必须确认**能否在 2027 年 2 月底结束**，否则会压掉暑期实习的投递时间。

**投递记录统一维护在** [docs/weekly-review.md](../docs/weekly-review.md) 的投递追踪表里。

## 二、技术资讯与学习

| 站点 | 用途 |
| --- | --- |
| [arXiv cs.CL / cs.DC](https://arxiv.org/list/cs.CL/recent) | 论文源头。**只看标题和摘要，不要陷进去** |
| [Hugging Face](https://huggingface.co/) | 模型与数据集，项目二取模型的地方 |
| [Papers with Code](https://paperswithcode.com/) | 找论文对应实现 |
| [LMSYS 博客](https://lmsys.org/blog/) | 推理优化的一手内容 |
| [Anthropic Engineering](https://www.anthropic.com/engineering) | agent 工程实践，质量最高的一批文章 |
| [OpenAI Cookbook](https://cookbook.openai.com/) | API 用法与最佳实践速查 |
| [Latent Space](https://www.latent.space/) | AI 工程方向的播客与 newsletter，通勤时间听 |
| [Hacker News](https://news.ycombinator.com/) | 看业界在讨论什么，每天 5 分钟上限 |

**信息摄入纪律**：每天刷资讯的时间上限 30 分钟。**焦虑感和进步不是同一回事**，刷十篇「agent 新突破」不如把项目里的一个数字测出来。

## 三、开发与实验工具

### 本地开发

| 工具 | 用途 |
| --- | --- |
| [uv](https://github.com/astral-sh/uv) | Python 包与虚拟环境管理，比 pip/conda 快一个量级 |
| [ruff](https://github.com/astral-sh/ruff) | lint + format，一个工具替代一整套 |
| `pytest` + `pytest-asyncio` | 测试，异步代码必备 |
| Docker Desktop / colima | 项目一的本地开发环境 |
| [kind](https://kind.sigs.k8s.io/) / minikube | 本地 K8s 集群，用来验证项目一的部署 manifest |

### 压测与观测

| 工具 | 用途 |
| --- | --- |
| [k6](https://k6.io/) 或 [locust](https://locust.io/) | 项目一的并发压测，出 p50/p99 数字 |
| `vllm bench` / `genai-perf` | 推理服务的吞吐与延迟压测 |
| [Langfuse](https://langfuse.com/) | agent trace 与 token 成本核算 |
| Prometheus + Grafana | 项目一的 metrics 面板 |
| `py-spy` | Python 性能火焰图，定位 CPU 热点 |
| `nvidia-smi` / `nvtop` | GPU 利用率与显存监控 |

### GPU 资源

学校没卡时的退路，**按小时租，跑完关键实验就停**：

- 各云厂商的按量付费 GPU 实例（阿里云、腾讯云、火山引擎）
- [Modal](https://modal.com/) / [RunPod](https://www.runpod.io/) 等按秒计费平台，适合短实验
- 免费额度：Kaggle（每周 GPU 配额）、Colab，够验证小模型的原理趋势

**实验预算纪律**：跑之前先估算花费，跑完立刻关机。租 GPU 忘关是最常见的血亏。

## 四、模型 API

项目开发需要至少一个可用的 API：

- OpenAI / Anthropic 官方 API（额度贵但兼容性最好，agent 场景效果最稳）
- 国内厂商 API（DeepSeek、Moonshot、通义、智谱等），性价比高，多数提供 OpenAI 兼容接口
- 本地模型（Ollama / vLLM + 小参数模型），调试循环逻辑时用它省钱

**成本纪律**：agent 死循环烧掉几百块是真实事故。**开发期就把最大步数和预算熔断写进代码**，这既省钱，也正好是面试里的加分回答。

## 五、维护约定

- 用过觉得不好的工具直接划掉并写一句原因，比留着占位有用
- 新发现的高质量站点加进来，但**总量控制住**——收藏夹越长，实际使用率越低
