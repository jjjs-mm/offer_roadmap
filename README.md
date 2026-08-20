# offer_roadmap

Agent Infra 方向求职冲刺 | Agent Runtime · Sandbox · LLM Serving · Eval | Python · Java · K8s

> 目标：12 月前入职一段日常实习（南京优先），2027 年 2 月底带着这段经历「开启即投」暑期实习（杭州主投、全国保底），正式工作倾向杭州。
> 周期：2026-08-20 → 2026-12-20，延伸至 2027-04 的暑期实习投递期。
> 起点：Java 后端基础，转向 agent infra——因为 agent 平台的核心难题（高并发、隔离、调度、可观测性）本质就是分布式后端问题。

## 从这里开始

| 文档 | 作用 |
| --- | --- |
| [docs/roadmap.md](docs/roadmap.md) | **主计划**。四个月分月安排 + 每周 checklist + 止损方案 |
| [projects/README.md](projects/README.md) | 三个项目的设计文档与必须测出的 benchmark 指标 |
| [docs/resume.md](docs/resume.md) | 简历骨架，量化占位待填 |
| [docs/interview.md](docs/interview.md) | 分类题库 + 真题记录 |
| [docs/weekly-review.md](docs/weekly-review.md) | 周复盘、投递追踪、能力自评、指标看板 |
| [leetcode/README.md](leetcode/README.md) | 刷题节奏、专题进度、错题本 |
| [resources/](resources/) | [论文与博客](resources/blogs.md) · [开源仓库](resources/github.md) · [书单](resources/books.md) · [站点与工具](resources/websites.md) |

## 四个月主线

```mermaid
flowchart LR
  M1["第 1 月<br/>手写 agent loop<br/>Python 工程化"] --> M2["第 2 月<br/>沙箱执行服务<br/>日常实习开投"]
  M2 --> M3["第 3 月<br/>推理压测 + eval<br/>拿下 offer"]
  M3 --> M4["第 4 月<br/>12月初入职实习<br/>节奏切换"]
  M4 --> M5["1-2月寒假<br/>全职产出"]
  M5 --> M6["2月底<br/>开启即投<br/>暑期实习"]
```

| 时间 | 主线 | 关键交付 |
| --- | --- | --- |
| 8/20 – 9/20 | 不用框架，从零手写 agent 运行时 | mini-agent + 4 篇博客 + 简历 v1 |
| 9/20 – 10/20 | Agent 代码执行沙箱服务 + **日常实习开投** | 压测报告 + 简历 v2 + 进入面试流程 |
| 10/20 – 11/20 | 面试优先，vLLM 压测与 eval 并行 | **日常实习 offer（硬指标）** + 吞吐延迟曲线 |
| 11/20 – 12/20 | **12 月初入职实习**，自学做减法 | 实习适应期通过 + 简历 v3 + 八股 80 题 |
| 2027/01 – 02 | 寒假全职实习，补完项目二 | 一段可量化的实习产出 |
| 2027/02 底 – 04 | **暑期实习投递与面试**（杭州主投、全国保底） | 暑期实习 offer |

## 三条不能违背的原则

1. **一个有数字的深度项目，胜过三个框架 demo。** 所有项目产出必须带 benchmark 数字，没有数字的项目等于没做。
2. **10 月就要投出日常实习，不要等准备好。** 12 月初入职是硬约束——2 月底投暑期实习时实习时长要满两个月，才能进「开启即投」那一档。
3. **算法不能丢。** 每天 1–2 题是底线。

## 目录结构

```
docs/        计划、简历、题库、周复盘
projects/    项目设计文档与代码
leetcode/    刷题记录与错题本
notes/       论文与源码阅读笔记
blog/        对外发布的技术博客
resources/   论文、开源仓库、书单、工具清单
scripts/     压测与自动化脚本
```

## 进度

关键指标看板见 [docs/weekly-review.md](docs/weekly-review.md#关键指标看板)。

- [ ] 项目 0：mini-agent
- [ ] 项目 1：agent 执行沙箱服务
- [ ] 项目 2：推理压测 + eval harness
- [ ] 1–2 个 merged 开源 PR
- [ ] **日常实习 offer（11 月底）→ 12 月初入职**
- [ ] 暑期实习 offer（2027 年 3–4 月）
