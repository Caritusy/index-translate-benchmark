# Index-Translate public API benchmark

对 `index-mt-2b`、`index-mt-9b`、`index-mt-35b` 的小样本公共接口实测，重点记录客户端完成时长和可核查的错译。包括准确请求提示、完整模型输出、原始时延和独立复现脚本。

测试时间为 **2026-10-10 20:06–20:08 UTC+08:00**。16 个质量样本各调用三个模型一次，另有 3 个测速样本各模型重复 5 次，共 **93 次正式请求，全部成功且未截断**。均为人工构造的示例文本。

## 结果

相同文本各重复 5 次的**完成时间中位数**，单位为秒；完成指客户端收到 SSE `[DONE]`。长段为 211 词英译中，输出约 390–418 个字符。

| 请求模型 | 日常短句 | 技术双句 | 长段 | 长段首字 | 长段完成范围 |
|---|---:|---:|---:|---:|---:|
| `index-mt-2b` | 0.51 | 0.46 | 1.16 | 0.30 | 1.15–1.36 |
| `index-mt-9b` | 0.65 | 0.70 | 2.97 | 0.37 | 2.91–3.04 |
| `index-mt-35b` | 0.73 | 0.85 | 2.45 | 0.44 | 2.22–4.01 |

本轮 **2B 最快，35B 在几个复杂语义样本上更准确**。2B/9B 在“增加到原来的 1.2 倍”上混淆了 `increase to` 和 `increase by`；2B 还将“暂停发布”译成了“暂停开发”。35B 也有局部问题，例如将任务状态 `pending` 译成“进行中”。日常句子、JSON、Markdown 和指定术语多数表现接近。

这些时间包含 HTTP/TLS 建连、网络、排队和生成。串行调用，轮换模型顺序；重复提示可能受缓存影响，服务器硬件与其他用户负载没有控制。**这是一轮公共部署体验，不能当作同硬件的模型推理性能排名。** 质量例子来自首轮单次输出，也不能代表错误率或全部语言的质量。

[完整报告与全部首轮译文](REPORT.zh-CN.md) · [原始结果](results/2026-10-10/results.jsonl) · [原始汇总](results/2026-10-10/summary.json)

## 快速复现

Python **3.10+**，仅标准库，无需安装包、GPU 或 API key。

```sh
git clone https://github.com/Caritusy/index-translate-benchmark.git
cd index-translate-benchmark
python benchmark.py
```

默认完整运行 93 次请求，保存到 `output/`。重新执行会恢复同一参数的运行，跳过已记录请求；想完整重跑时指定新目录。`output/` 默认不进入 Git。

只复现两个核心错误样本（6 次请求）：

```sh
python benchmark.py --quality-only --case budget --case technical --output-dir output-errors
```

只运行重复测速：

```sh
python benchmark.py --speed-only --repeats 5 --output-dir output-speed
```

只测一个模型、或修改 endpoint：

```sh
python benchmark.py --quality-only --models index-mt-2b --output-dir output-2b
python benchmark.py --api-base https://index-translate.bilibili.com/v1 --output-dir output-new
```

不访问网络，仅重新统计已有记录：

```sh
python benchmark.py --summarize --output-dir results/2026-10-10
```

最后一条会重写该目录下的 `summary.json`；新脚本的汇总结构可能与留存的原始汇总不同，原始值可通过 Git 恢复。脚本输出的路径均为可移植的相对路径。

## 请求与数据

公开接口：`https://index-translate.bilibili.com/v1/chat/completions`。统一参数：

```json
{
  "temperature": 0,
  "max_tokens": 2048,
  "stream": true,
  "stream_options": {"include_usage": true},
  "chat_template_kwargs": {"enable_thinking": false}
}
```

请求只有一条 user message，其内容直接取 `data/cases.json` 对应样本的 `prompt`。这些提示与原始实测完全一致，复现脚本无需导入原来本地的调用文件。

| 文件 | 内容 |
|---|---|
| `benchmark.py` | 独立请求、SSE 计时、恢复与汇总脚本 |
| `data/cases.json` | 16 个源文、语言、约束、准确提示和检查重点 |
| `results/2026-10-10/results.jsonl` | 93 次完整译文、TTFT、完成时间、usage、模型返回名 |
| `results/2026-10-10/summary.json` | 原始实测统计 |
| `results/2026-10-10/constraint_checks.json` | JSON、Markdown、术语的程序检查 |
| `REPORT.zh-CN.md` | 详细方法、时长、错译分析和逐条输出 |
| `docs/upstream-issue.md` | 上游 issue 正文 |

只保留复现需要的测量字段；不包含本地绝对路径、系统用户名、机器名、IP、访问令牌或私人文本。模型返回的模型名、token 计数和测量时间保留，用于解释部署行为。生成新的请求不会保证得到逐字相同的译文或时延。

上游项目：[bilibili/Index-Translate](https://github.com/bilibili/Index-Translate)。反馈已发布为 [Issue #18](https://github.com/bilibili/Index-Translate/issues/18)。本仓库是独立反馈材料。
