# 阅读笔记

论文、源码、技术博客的私人笔记。**和 [../blog/](../blog/) 的区别**：这里是给自己看的草稿，可以零散；`blog/` 是打磨过、能放进简历的对外产出。

## 组织方式

```
notes/
  papers/     论文笔记，文件名用 短标题-年份.md
  source/     源码阅读笔记，文件名用 仓库名-模块.md
  topics/     专题整理（面试八股的沉淀），如 kv-cache.md
```

## 论文笔记模板

```markdown
# 标题（arXiv 链接）

**日期**：YYYY-MM-DD | **类别**：agent / 推理 / 系统

## 它解决什么问题
## 关键洞察（一到三条）
## 方法（要能凭这段自己画出图）
## 实验里最关键的一张表说明了什么
## 局限（面试里能说出局限，比背下方法更值钱）
## 如果让我实现，最难的地方在哪
```

## 源码笔记模板

```markdown
# 仓库 / 模块

**日期**：YYYY-MM-DD | **版本 / commit**：

## 模块划分与调用链
## 核心抽象（它把什么东西建模成了什么）
## 学到的设计（可以搬到我项目里的）
## 我觉得可以改进的地方（潜在 PR 素材）
## 遗留疑问
```

## 专题整理

面试八股不要临时抱佛脚。读到相关内容时就往对应专题文件里追加，第 4 月直接拿来复习。建议建的专题，对应 [../docs/interview.md](../docs/interview.md) 的分类：

- `kv-cache.md`、`continuous-batching.md`、`quantization.md`
- `context-engineering.md`、`tool-calling-reliability.md`、`agent-eval.md`
- `container-isolation.md`、`cold-start.md`
- `rag-pipeline.md`

## 纪律

**读完必须留下笔记，否则等于没读。** 一周后回想不起来的内容，在面试里也讲不出来。
