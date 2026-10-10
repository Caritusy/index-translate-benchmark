做了一轮免费公共 API 的小样本对比，想反馈 **2B / 9B / 35B 的客户端响应时长，以及几处可以复现的语义错译**，供回归排查参考。

复现仓库：**https://github.com/Caritusy/index-translate-benchmark**

- [准确提示与源文](https://github.com/Caritusy/index-translate-benchmark/blob/main/data/cases.json)
- [93 次原始输出和计时](https://github.com/Caritusy/index-translate-benchmark/blob/main/results/2026-10-10/results.jsonl)
- [完整报告与逐条译文](https://github.com/Caritusy/index-translate-benchmark/blob/main/REPORT.zh-CN.md)

### 测试方法

- 时间：2026-10-10 20:06–20:08，UTC+08:00。
- Endpoint：`https://index-translate.bilibili.com/v1/chat/completions`。
- 请求模型：`index-mt-2b`、`index-mt-9b`、`index-mt-35b`，三个名称均实际调用成功。
- `temperature=0`、`max_tokens=2048`、`stream=true`、`stream_options.include_usage=true`、`chat_template_kwargs.enable_thinking=false`；单条 user message。
- 16 个质量样本 × 3 个模型 = 48 次；另外 3 个测速样本 × 每模型 5 次 × 3 个模型 = 45 次；共 **93 次正式请求，全部成功，finish_reason 为 stop**。简短探测和预热请求没有计入。
- 请求串行执行并轮换模型顺序。首字时间从发送请求计到首个非空 content；完成时间计到 SSE `[DONE]`。包含网络、建连、排队及生成，不是服务端纯推理时长。

### 1. 完成时长

以下是同一文本各重复 **5 次的中位数**，单位为秒。

| 请求模型 | 日常短句完成 | 技术双句完成 | 211 词英译中长段完成 | 长段首字 | 长段完成范围 |
|---|---:|---:|---:|---:|---:|
| `index-mt-2b` | 0.51 | 0.46 | 1.16 | 0.30 | 1.15–1.36 |
| `index-mt-9b` | 0.65 | 0.70 | 2.97 | 0.37 | 2.91–3.04 |
| `index-mt-35b` | 0.73 | 0.85 | 2.45 | 0.44 | 2.22–4.01 |

本轮 2B 的长段完成用时约为 35B 的 48%、9B 的 39%；35B 的长段中位数反而比 9B 更短，但有一次达到 4.01 秒。长段输出约 390–418 个字符，完整输出可在原始结果中核对。另一个 453 字符中译英长段的首轮单次完成用时为 2B 1.60 秒、9B 4.16 秒、35B 2.95 秒，**这条只测了一次，没有混入重复测速中位数**。

重复提示可能受缓存影响，部署硬件、量化方式和其他用户负载没有控制，因此这里只描述公共服务在该时间段的体验，不能推断同硬件上的模型性能。流式返回名分别为 `qwen35-2b-linear-merge`、`qwen35-9b-6624275-iter999`、`Index-Translate-35B-A3B`；想请教三个公共路由的部署差异是否能解释上述时长现象。

### 2. 错译：增加到 vs 增加了（2B / 9B）

样本 `budget`，中译英；完整源文：

> 预算最多增加到原来的1.2倍，而不是增加1.2倍。除非供应商在周五之前确认交期，否则我们不会付款。

2B：

> The budget can be increased **by a maximum of 1.2 times the original amount**, not by 1.2 times. We will not make the payment unless the supplier confirms the delivery date by Friday.

9B：

> The budget can be increased **by up to 1.2 times the original amount**, not by 1.2 times. We will not make payment unless the supplier confirms the delivery date by Friday.

应保留 `increase to 1.2 times` / `increase by at most 20%`。当前两版把最终值 120% 写成增加额 120%，并与后半句 `not by 1.2 times` 矛盾。这是本轮最明显的数量逻辑问题。

35B 的同提示输出是：

> The budget can be increased by a maximum of **20% (to 1.2 times the original amount)**, not increased by 1.2 times. We will not make the payment unless the supplier confirms the delivery date by Friday.

### 3. 错译：暂停发布 → 暂停开发（2B）

样本 `long_en_zh`，三段服务中断说明，英译中。相关源句：

> The new **release** has been paused, not permanently cancelled.

2B：

> 新版本已暂停**开发**，并未永久取消。

原文描述暂停版本发布，并未说停止开发。9B 为“新的版本发布已被暂停，但并非永久取消”，35B 为“新版本发布已暂停，但并未永久取消”。这是长段中的上下文/活动类型混淆；复现时请使用仓库中保存的完整三段提示，不能保证只截取一句能得到同样译法。

### 4. 错译：操作约束被弱化（2B）

样本 `technical`，英译中；完整源文：

> The client application keeps timing out, even though the server is up. Please close the current session **without terminating the process**, then open a new session.

2B：

> 客户端应用程序持续出现超时问题，尽管服务器已正常运行。请关闭当前会话（但**无需终止进程**），然后打开新会话。

`without terminating` 要求操作期间保持进程运行；“无需终止”只表达不必要，弱化了“不终止”的约束。9B 为“不要终止进程”，35B 为“在不终止进程的情况下”，更贴近原意。

### 5. 状态语义问题：pending → 进行中（35B）

仍是 `long_en_zh` 的完整长段。相关源句：

> If an upload is still marked as **pending**, please check whether it completed before starting it again; otherwise, you may create a duplicate.

35B：

> 如果某次上传仍标记为“**进行中**”，请先确认其是否已完成，再决定是否重新发起；否则可能会导致文件重复。

在常见任务状态区分下，`pending` 更贴近“待处理/待完成”，`in progress` 才是“进行中”；当前译法可能改变状态含义。2B/9B 均用了“待处理”。这里作为状态术语不够精确的例子反馈，具体产品若将 pending 用作泛指未完成，则严重程度会不同。

### 快速复现

仅 Python 3.10+ 标准库，无依赖安装。脚本直接读取留存的准确提示，不依赖任何本地调用文件。

```sh
git clone https://github.com/Caritusy/index-translate-benchmark.git
cd index-translate-benchmark

# 完整实测：93 次请求
python benchmark.py

# 复现上述语义例子：3 个样本 × 3 模型 = 9 次请求
python benchmark.py --quality-only --case budget --case technical --case long_en_zh --output-dir output-errors

# 只测时长：默认 3 个样本 × 5 次 × 3 模型 = 45 次
python benchmark.py --speed-only --repeats 5 --output-dir output-speed
```

以上质量例子都是首轮单次输出，不代表统计错误率；新请求可能因模型更新、路由或服务状态而不同。日常句子、数量否定、部署顺序及 JSON/Markdown 格式多数没有实质差异，三个模型均通过本轮格式/术语检查。复现材料已移除本地绝对路径、系统用户名及其他不必要的环境信息，源文均为构造示例。

希望这些具体例子能用于数量逻辑、发布/开发语义和操作约束的回归，也希望能了解公共 API 三个模型路由的时长差异。
