# 脚本

压测、评测、自动化脚本。**核心要求：任何人 clone 下来都能复现你简历上的每一个数字。**

面试官问「这个 p99 是怎么测出来的」时，你能直接指向这里的脚本和它的输出——这比口头解释可信得多。

## 组织方式

```
scripts/
  bench/       压测脚本（沙箱冷启动、并发、推理吞吐）
  eval/        评测运行与报告生成
  setup/       环境准备（起集群、拉模型、造测试数据）
  results/     压测与评测的原始输出，按日期归档
```

## 压测脚本要求

每个压测脚本必须做到：

1. **参数化**：并发数、请求数、目标地址、超时都从命令行或配置文件传入，不写死
2. **输出结构化结果**：JSON 或 CSV 存进 `results/`，文件名带时间戳和配置摘要
3. **报告分位数而非均值**：p50 / p90 / p99 / max。**均值会掩盖长尾，而长尾才是线上事故的来源**
4. **记录环境**：机器规格、镜像版本、模型版本、commit hash 一起写进结果文件
5. **预热后再计时**：丢弃前 N 次请求，避免 JIT / 缓存 / 连接建立污染数据

## 结果归档命名

```
results/sandbox-coldstart_20261015_pool-on_c50.json
results/vllm-throughput_20261101_bs32_prefix-cache-on.json
```

配置写进文件名，回头对比 before/after 时不用打开文件猜。

## 常用脚本清单（随项目进展补齐）

| 脚本 | 用途 | 对应项目 |
| --- | --- | --- |
| `bench/sandbox_coldstart.py` | 沙箱冷启动分位数（池化 开/关 对比） | 项目一 |
| `bench/sandbox_concurrency.py` | 并发会话数与吞吐上限 | 项目一 |
| `bench/sandbox_security.sh` | 逃逸测试套件（路径逃逸、fork bomb、内存炸弹、外网访问） | 项目一 |
| `bench/chaos_orphan.py` | 混沌测试后统计孤儿容器泄漏率 | 项目一 |
| `bench/vllm_sweep.py` | 扫 batch size / 并发，出吞吐-延迟曲线 | 项目二 |
| `bench/prefix_cache_ab.py` | prefix caching 开关的 A/B 对比 | 项目二 |
| `eval/run_eval.py` | 一条命令跑完整 agent 评测 | 项目二 |
| `eval/report.py` | 生成指标表与失败归因分布 | 项目二 |

## 纪律

**先测 baseline 再优化。** 优化完才想起没存优化前的数字，是最常见也最痛的失误——你会失去简历上最值钱的那个 before/after 对比。
