# Index MT 三模型实测报告

实测时间：2026-10-10 20:06–20:08（北京时间）。

**本轮建议：重视翻译质量选 `index-mt-35b`；重视速度选 `index-mt-2b`。** `index-mt-9b` 在部分样本上比 2B 更准确，但本轮既未成为质量最好的模型，也未成为最快的模型。

## 测试方法

使用用户提供的 `llmapi.py` 中的 `build_prompt` 构造提示，调用其公共接口；公开复现脚本直接读取 `data/cases.json` 中保存的原始提示，无需该本地文件。三个请求模型名均使用用户给出的名称，并已实际验证可调用。`GET /v1/models` 只列出默认 35B，不能据此判断另外两个模型不可用。

共 16 个质量样本，每个模型各翻译一次；另选日常短句、技术双句、英译中长段，每个模型各重复 5 次。正式请求总计 93 次（每模型 31 次），全部 HTTP 成功、输出非空且以 `stop` 完成；探测与预热请求不计入统计。

质量覆盖中英双向、习语、倍数、否定、技术操作、日语、德语、术语表、JSON、Markdown，以及两篇三段长文。长段英译中原文为 211 个英文单词；长段中译英原文为 453 个字符。

统一参数：temperature=0，max_tokens=2048，stream=true，enable_thinking=false。请求串行执行，每个样本轮换模型调用顺序。计时使用客户端单调时钟，首字时间为收到首个非空 content 的时间；完成时间为收到流式 DONE 的时间，包含建连、网络、服务器排队和生成。

重复测速使用已发送过的相同提示，可能受服务器提示缓存影响；没有清缓存或控制其他用户的负载。质量首轮也不是完全冷启动，因为此前做过简短预热。以下是本机在当时公共部署上的体验，不能直接外推为模型在相同硬件上的纯推理能力。

## 重复测速结果

以下均为 5 次测量的中位数，单位为秒；表中长段是同一篇 211 词英译中。

| 模型 | 日常短句完成 | 技术双句完成 | 长段完成 | 长段首字 | 长段用时范围 |
|---|---:|---:|---:|---:|---:|
| index-mt-2b | 0.51 | 0.46 | 1.16 | 0.30 | 1.15–1.36 |
| index-mt-9b | 0.65 | 0.70 | 2.97 | 0.37 | 2.91–3.04 |
| index-mt-35b | 0.73 | 0.85 | 2.45 | 0.44 | 2.22–4.01 |

2B 的长段完成用时约为 35B 的 48%、9B 的 39%。35B 的长段中位数比 9B 更快，但有一次达到 4.01 秒，波动大于本轮 9B；这不意味着任何时段都能保证这一排序。首字时间不完全按模型大小排序，完整输出时间更能体现本轮速度差距。

## 首轮 16 个样本的时间

样本长度混合，以下中位数仅用于观察该组样本，不能理解为任意文章都能在这一时间内完成。

| 模型 | 首字中位数 | 完成中位数 | 长段中译英完成（单次） | 成功请求 |
|---|---:|---:|---:|---:|
| index-mt-2b | 0.29 | 0.45 | 1.60 | 31/31 |
| index-mt-9b | 0.31 | 0.67 | 4.16 | 31/31 |
| index-mt-35b | 0.45 | 0.75 | 2.95 | 31/31 |

## 质量差异与依据

日常句子、数量否定、部署顺序、德译中，以及 JSON/Markdown 格式整体差异不大，三个模型都能完成。JSON 输出均可解析、key 与元数据保持不变；Markdown 的两个占位符、URL、反引号代码及基本结构均保留；术语约束中四个指定英文术语全部出现，重复术语一致。上述约束由程序检查，语义由逐条复核判断。

| 样本 | 2B | 9B | 35B |
|---|---|---|---|
| 增加到原来的 1.2 倍 | `increased by ... 1.2 times`，把增加到和增加了混淆 | 同样用了 `increased by ... 1.2 times` | 明确写出 `20% (to 1.2 times the original amount)` |
| The new release has been paused | 译为“新版本已暂停开发”，将发布暂停改成开发暂停 | “新的版本发布已被暂停” | “新版本发布已暂停” |
| 日语委婉拒绝、条件改变后重新商谈 | 增添“该方案”；把再次商谈请求改成“请再与我们联系” | 将含糊的“採用”具体化为“录用”，并增添“请随时与我们联系” | 采用较中性的“暂不采用”，保留再次商谈方向 |
| 不终止进程而关闭会话 | “无需终止进程”将约束语气弱化 | “不要终止进程” | “在不终止进程的情况下” |

35B 也不是每条都完美：口语样本将“关键时刻却掉链子”加上了 `always`，扩大了原句的频率含义；9B 在同一条也有这个问题。英译中长段的 `pending` 被 35B 译成“进行中”，而 2B/9B 的“待处理”更贴近该状态。日语“採用”在无上下文时可指采用方案或录用人员，单独这一句不能当作确定的招聘误译，因此更看重译文是否保留歧义和是否改变联系主体。2B 将 `service credit` 译成“服务补偿金”，也比原文的服务抵扣/账户信用补偿更具体；9B/35B 的“服务补偿”未限定现金形式。

2B 的普通翻译和格式遵从已相当可用，主要风险出现在需要精确理解倍数、操作约束、专业上下文的时候。本轮证据支持复杂或重要文本优先用 35B，普通网页、聊天和大量文本优先用 2B；不足以推断所有语言或领域都保持同样排名。

## 复现材料

- `benchmark.py`：独立 Python 标准库脚本，直接发送保存的原始提示。
- `data/cases.json`：16 条源文、准确请求提示、约束和检查重点。
- `results/2026-10-10/results.jsonl`：93 条原始输出、时延、usage 和完成状态。
- `results/2026-10-10/summary.json`：原始统计汇总。
- `results/2026-10-10/constraint_checks.json`：格式与术语程序检查。

运行方法见仓库根目录 `README.md`。人工分析中参考了隐藏模型名称的模型辅助复核；本报告没有把这种主观评分当作标准基准。

## 全部首轮译文

### everyday_en_zh · 日常 · en→zh

原文：

```text
The train leaves at 6:45 tomorrow morning. Please arrive at least fifteen minutes early and bring the ticket on your phone.
```

检查重点：保留次日早上6:45、至少提前15分钟、手机中的车票。

**index-mt-2b**（首字 0.319s；完成 0.399s）

```text
火车明天早上6点45分出发。请至少提前十五分钟到达，并携带手机上的车票。
```

**index-mt-9b**（首字 0.309s；完成 0.535s）

```text
火车明天早上6点45分发车。请至少提前15分钟到达，并携带手机上的车票。
```

**index-mt-35b**（首字 0.496s；完成 0.701s）

```text
火车将于明天早上6:45发车。请至少提前15分钟到达，并准备好手机上的车票。
```

### everyday_zh_en · 日常 · zh→en

原文：

```text
麻烦帮我把窗户关一下，外面有点冷。你如果还没吃饭，冰箱里有昨天做的汤，热一下就能喝。
```

检查重点：礼貌语气；如果尚未吃饭；冰箱里的昨天做的汤，需加热。

**index-mt-2b**（首字 0.300s；完成 0.516s）

```text
Could you please close the window? It's a bit cold outside. If you haven't eaten yet, there's soup from yesterday in the fridge. Just heat it up and you can drink it.
```

**index-mt-9b**（首字 0.334s；完成 0.776s）

```text
Could you please close the window? It's a bit cold outside. If you haven't eaten yet, there's some soup from yesterday in the fridge—just heat it up and you're good to go.
```

**index-mt-35b**（首字 0.451s；完成 0.749s）

```text
Could you please close the window? It's a bit cold outside. If you haven't eaten yet, there's some soup made yesterday in the fridge. Just heat it up and it's ready to drink.
```

### negation · 数量与否定 · en→zh

原文：

```text
Of the 120 applications, all but 17 were approved. No applicant under 18 was accepted, even if they had parental consent.
```

检查重点：120份中除17份外都获批，即103获批；未满18岁无人获批，家长同意也不例外。

**index-mt-2b**（首字 0.293s；完成 0.407s）

```text
在120份申请中，除17份外，其余全部获批。即使有父母同意，也没有18岁以下申请人被接受。
```

**index-mt-9b**（首字 0.305s；完成 0.673s）

```text
在120份申请中，除17份外，其余全部获得批准。即使有父母同意，也没有任何未满18岁的申请人被接受。
```

**index-mt-35b**（首字 0.458s；完成 0.716s）

```text
在120份申请中，除17份外均获批准。任何未满18岁的申请人均未被接受，即使他们已获得父母同意。
```

### budget · 倍数与条件 · zh→en

原文：

```text
预算最多增加到原来的1.2倍，而不是增加1.2倍。除非供应商在周五之前确认交期，否则我们不会付款。
```

检查重点：增加到原来的1.2倍，不能误作增加120%；周五之前确认交期是付款必要条件。

**index-mt-2b**（首字 0.294s；完成 0.466s）

```text
The budget can be increased by a maximum of 1.2 times the original amount, not by 1.2 times. We will not make the payment unless the supplier confirms the delivery date by Friday.
```

**index-mt-9b**（首字 0.290s；完成 0.746s）

```text
The budget can be increased by up to 1.2 times the original amount, not by 1.2 times. We will not make payment unless the supplier confirms the delivery date by Friday.
```

**index-mt-35b**（首字 0.419s；完成 0.830s）

```text
The budget can be increased by a maximum of 20% (to 1.2 times the original amount), not increased by 1.2 times. We will not make the payment unless the supplier confirms the delivery date by Friday.
```

### idiom_en_zh · 习语 · en→zh

原文：

```text
I see where you're coming from, but let's not throw the baby out with the bathwater. Could we sleep on it and touch base tomorrow?
```

检查重点：理解对方观点；不因局部问题全盘抛弃；考虑一晚明天再沟通；保持商量语气。

**index-mt-2b**（首字 0.255s；完成 0.343s）

```text
我理解你的意思，但让我们不要一竿子打死。我们可以再考虑一下，明天再联系吗？
```

**index-mt-9b**（首字 0.337s；完成 0.547s）

```text
我理解你的想法，但我们不能因噎废食。要不我们先睡一觉，明天再讨论吧？
```

**index-mt-35b**（首字 0.454s；完成 0.650s）

```text
我理解你的意思，但我们不能因噎废食。不如我们先冷静考虑一下，明天再联系？
```

### idiom_zh_en · 口语 · zh→en

原文：

```text
他嘴上说这事十拿九稳，真到关键时刻却掉链子。你可别把他那句“我尽量”当成承诺。
```

检查重点：声称有把握、关键时刻失误；我尽量不是承诺；避免机械直译。

**index-mt-2b**（首字 0.252s；完成 0.440s）

```text
He said it was a sure thing, but he really let you down at the critical moment. Don't take his "I'll do my best" as a promise.
```

**index-mt-9b**（首字 0.274s；完成 0.647s）

```text
He claims it's a sure thing, but he always drops the ball at the critical moment. Don't take his "I'll do my best" as a promise.
```

**index-mt-35b**（首字 0.408s；完成 0.680s）

```text
He claims it's a sure thing, but he always lets you down when it really matters. Don't take his "I'll do my best" as a promise.
```

### technical · 技术语义 · en→zh

原文：

```text
The client application keeps timing out, even though the server is up. Please close the current session without terminating the process, then open a new session.
```

检查重点：客户端不断超时而服务器在运行；结束会话但不终止进程；新建会话。

**index-mt-2b**（首字 0.248s；完成 0.360s）

```text
客户端应用程序持续出现超时问题，尽管服务器已正常运行。请关闭当前会话（但无需终止进程），然后打开新会话。
```

**index-mt-9b**（首字 0.304s；完成 0.588s）

```text
客户端应用程序持续出现超时，但服务器仍在运行。请关闭当前会话（不要终止进程），然后打开一个新的会话。
```

**index-mt-35b**（首字 0.429s；完成 0.656s）

```text
客户端应用程序持续超时，尽管服务器正在运行。请在不终止进程的情况下关闭当前会话，然后打开一个新会话。
```

### deployment · 术语与顺序 · zh→en

原文：

```text
预发布环境已通过回归测试，但生产环境仍未部署新版本。请先备份生产数据库，再执行迁移；如果迁移失败，只回滚这次事务，不要撤销整个部署。
```

检查重点：staging/regression/production/migration/transaction/deployment术语准确；先备份再迁移；仅回滚本次事务。

**index-mt-2b**（首字 0.306s；完成 0.579s）

```text
The pre-release environment has passed regression tests, but the new version has not yet been deployed to the production environment. Please back up the production database first before running the migration. If the migration fails, only roll back this transaction; do not undo the entire deployment.
```

**index-mt-9b**（首字 0.306s；完成 0.862s）

```text
The pre-release environment has passed regression testing, but the new version has not yet been deployed to the production environment. Please back up the production database before executing the migration. If the migration fails, roll back only this transaction and do not revert the entire deployment.
```

**index-mt-35b**（首字 0.403s；完成 0.875s）

```text
The pre-release environment has passed regression testing, but the new version has not yet been deployed to the production environment. Please back up the production database before executing the migration. If the migration fails, only roll back this transaction; do not undo the entire deployment.
```

### ja_zh · 日译中 · ja→zh

原文：

```text
検討した結果、今回は採用を見送ることにしました。ご期待に添えず申し訳ありませんが、条件が変わりましたら、改めてご相談させてください。
```

检查重点：考虑后本次不采用/暂缓采用；礼貌拒绝；条件变化后重新商谈。上下文没指明员工，不应武断增添招聘事实。

**index-mt-2b**（首字 0.273s；完成 0.389s）

```text
经过讨论，我们决定这次不采用该方案。很抱歉未能满足您的期望，如果条件有变化，请再与我们联系。
```

**index-mt-9b**（首字 0.277s；完成 0.617s）

```text
经过慎重考虑，我们决定此次不予录用。很抱歉未能满足您的期望，但如果条件有所变化，请随时与我们联系，我们将再次与您商谈。
```

**index-mt-35b**（首字 0.456s；完成 0.709s）

```text
经过讨论，我们决定本次暂不采用。很抱歉未能满足您的期望，但如有条件变更，我们将再次与您商谈。
```

### zh_ja · 中译日 · zh→ja

原文：

```text
这次会议改到下周三下午三点，地点不变。如果你来不了，请提前一天告诉我，不用专门请假。
```

检查重点：改为下周三下午3点；地点不变；不能来提前一天告知；无需专门请假。

**index-mt-2b**（首字 0.235s；完成 0.365s）

```text
今回の会議は来週水曜日の午後3時に変更します。場所はこれまでと同じです。来られない場合は、1日前に連絡してください。わざわざ休暇を取る必要はありません。
```

**index-mt-9b**（首字 0.273s；完成 0.665s）

```text
今回の会議は来週の水曜日の午後3時に変更しますが、場所は変わりません。もし来られない場合は、前日までに教えてください。わざわざ休暇を申請する必要はありません。
```

**index-mt-35b**（首字 0.429s；完成 0.769s）

```text
今回の会議は来週の水曜日の午後3時に延期します。場所は変更ありません。もしご来場が難しい場合は、前日までにその旨をお知らせください。正式な休暇届は不要です。
```

### de_zh · 德译中 · de→zh

原文：

```text
Das Update wird standardmäßig aktiviert, lässt sich aber in den Einstellungen deaktivieren. Bereits gespeicherte Daten werden dabei nicht gelöscht. Die Änderung gilt erst ab dem nächsten Neustart.
```

检查重点：默认启用而可在设置禁用；已存数据不删除；下次重启才生效。

**index-mt-2b**（首字 0.294s；完成 0.404s）

```text
该更新默认已激活，但可以在设置中禁用。已保存的数据在此过程中不会被删除。此更改将在下一次重启后生效。
```

**index-mt-9b**（首字 0.280s；完成 0.551s）

```text
该更新默认处于启用状态，但可以在设置中将其禁用。已保存的数据不会被删除。此更改将在下次重启后生效。
```

**index-mt-35b**（首字 0.430s；完成 0.657s）

```text
该更新默认处于激活状态，但可以在设置中将其停用。已保存的数据不会被删除。此更改仅在下次重启后生效。
```

### glossary · 术语约束 · zh→en

原文：

```text
星桥的灰度发布采用熔断器保护上游服务。若灰度发布失败，星桥会触发熔断器并回滚。
```

术语表：`{"星桥":"StarBridge","灰度发布":"canary release","熔断器":"circuit breaker","上游服务":"upstream services"}`

检查重点：指定术语精确保留，重复使用需一致；失败则触发熔断器和回滚。

**index-mt-2b**（首字 0.267s；完成 0.457s）

```text
StarBridge's canary release uses a circuit breaker to protect upstream services. If the canary release fails, StarBridge will trigger the circuit breaker and roll it back.
```

**index-mt-9b**（首字 0.337s；完成 0.666s）

```text
StarBridge's canary release uses a circuit breaker to protect upstream services. If the canary release fails, StarBridge will trigger the circuit breaker and roll back.
```

**index-mt-35b**（首字 0.466s；完成 0.756s）

```text
StarBridge uses a circuit breaker to protect upstream services during a canary release. If the canary release fails, StarBridge will trigger the circuit breaker and roll back.
```

### json · JSON约束 · zh→en

原文：

```text
{"title":"连接失败","message":"无法连接到服务器，请稍后重试。","button":"重新连接","version":"1.2.0","retry_count":3,"url":"https://example.com/help"}
```

附加约束：严格保留合法 JSON 格式，仅翻译中文字符串值。所有 key、数字、版本号和 URL 保持不变。

检查重点：只输出合法JSON；key不变；retry_count数字3；version及url不变；译值语义正确。

**index-mt-2b**（首字 0.284s；完成 0.458s）

```text
{"title":"Connection Failed","message":"Unable to connect to the server. Please try again later.","button":"Reconnect","version":"1.2.0","retry_count":3,"url":"https://example.com/help"}
```

**index-mt-9b**（首字 0.356s；完成 0.916s）

```text
{"title":"Connection Failed","message":"Unable to connect to the server. Please try again later.","button":"Reconnect","version":"1.2.0","retry_count":3,"url":"https://example.com/help"}
```

**index-mt-35b**（首字 0.480s；完成 0.832s）

```text
{"title":"Connection Failed","message":"Unable to connect to the server. Please try again later.","button":"Reconnect","version":"1.2.0","retry_count":3,"url":"https://example.com/help"}
```

### markdown · 格式与占位符 · zh→en

原文：

```text
## 同步状态
- 用户 **{username}**：已同步 {count} 个文件。
- 如需帮助，请访问 [帮助中心](https://example.com/help)。

`sync --dry-run` 仅预览操作，不会修改文件。
```

附加约束：保持 Markdown 结构、占位符 {username} 和 {count}、URL 和反引号内代码完全不变，只翻译中文文本。

检查重点：Markdown结构及占位符、URL、代码不变；dry-run仅预览不修改文件。

**index-mt-2b**（首字 0.295s；完成 0.525s）

```text
## Sync Status
- User **{username}**: Has synced {count} files.
- For help, please visit the [Help Center](https://example.com/help).

`sync --dry-run` only provides a preview of the operation and will not modify any files.
```

**index-mt-9b**（首字 0.347s；完成 1.034s）

```text
## Sync Status
- User **{username}**: {count} files have been synced.
- For help, please visit the [Help Center](https://example.com/help).

`sync --dry-run` only previews the operation and does not modify files.
```

**index-mt-35b**（首字 0.431s；完成 0.860s）

```text
## Synchronization Status
- User **{username}**: {count} files have been synchronized.
- For help, please visit [Help Center](https://example.com/help).

`sync --dry-run` only previews the operation and will not modify any files.
```

### long_en_zh · 长段英译中 · en→zh

原文：

```text
We are writing to clarify the service interruption that occurred on Tuesday. Between 09:10 and 09:47, some users could sign in but could not upload new files. Existing files remained available, and we found no evidence that customer data had been lost or accessed without authorization. The incident affected approximately 8% of upload requests in the Asia-Pacific region; it did not affect every customer in that region.

The immediate cause was a configuration change that reduced the number of available database connections. Automatic retries increased the load instead of relieving it. We restored the previous configuration at 09:32, but the backlog took another fifteen minutes to clear. The new release has been paused, not permanently cancelled. Before trying again, we will test the retry policy under load and add an alert for connection exhaustion.

Customers do not need to reset their passwords or re-upload files that already appear in their accounts. If an upload is still marked as pending, please check whether it completed before starting it again; otherwise, you may create a duplicate. We will issue a service credit only to eligible accounts, in accordance with their contracts. This notice is an explanation of what happened and should not be read as a promise that similar incidents can never occur.
```

检查重点：完整三段；8%是上传请求非所有客户；09:32恢复配置，15分钟清队列；暂停非永久取消；无需重置密码；仅合资格账户补偿；保留限定语与否定。

**index-mt-2b**（首字 0.261s；完成 1.120s）

```text
我们写此函是为了澄清周二发生的服务中断情况。在09:10至09:47期间，部分用户能够登录，但无法上传新文件。现有文件仍可正常访问，我们未发现客户数据丢失或未经授权被访问的证据。此次事件影响了亚太地区约8%的上传请求，但并未影响该地区的每一位客户。

直接原因是配置变更导致可用数据库连接数量减少。自动重试机制反而增加了负载，而非减轻其压力。我们在09:32恢复了之前的配置，但积压任务仍需要十五分钟才能清空。新版本已暂停开发，并未永久取消。在再次尝试前，我们将测试负载下的重试策略，并增加连接耗尽的警报功能。

客户无需重置密码或重新上传已存在于其账户中的文件。如果某个上传任务仍显示为待处理，请在重新尝试前确认其是否已完成；否则可能会创建重复任务。我们将根据客户合同，仅向符合条件的账户发放服务补偿金。本通知旨在解释事件发生情况，不应被理解为类似事件将永远不会再次发生的承诺。
```

**index-mt-9b**（首字 0.360s；完成 2.914s）

```text
我们特此致函，说明周二发生的服务中断情况。在09:10至09:47期间，部分用户虽然可以登录，但无法上传新文件。现有文件仍可正常访问，且我们未发现客户数据丢失或遭未经授权访问的证据。此次事件影响了亚太地区约8%的上传请求，但并非该地区所有客户都受到了影响。

此次事件的直接原因是配置变更导致可用数据库连接数减少。自动重试机制反而加重了系统负载，而非缓解问题。我们已于09:32恢复了之前的配置，但系统仍需额外15分钟才能处理完积压的请求。新的版本发布已被暂停，但并非永久取消。在再次尝试之前，我们将在高负载环境下测试重试策略，并增加连接耗尽的警报机制。

客户无需重置密码，也无需重新上传已存在于账户中的文件。如果某次上传仍显示为“待处理”，请在重新尝试前确认其是否已完成；否则可能会导致重复上传。我们将根据合同条款，仅向符合条件的账户提供服务补偿。本通知旨在解释事件经过，不应被理解为类似事件绝不会再次发生的承诺。
```

**index-mt-35b**（首字 0.648s；完成 2.752s）

```text
我们特此致函，旨在澄清周二发生的服务中断事件。在 09:10 至 09:47 期间，部分用户能够登录，但无法上传新文件。原有文件仍可正常访问，且我们未发现任何客户数据丢失或被未经授权访问的证据。此次事件影响了亚太地区约 8% 的上传请求，并非该地区所有客户均受到影响。

直接原因是某项配置变更导致可用数据库连接数减少。自动重试机制反而增加了系统负载，而非缓解负载。我们已于 09:32 恢复了之前的配置，但积压的请求又花了十五分钟才处理完毕。新版本发布已暂停，但并未永久取消。在重新尝试前，我们将在负载环境下测试重试策略，并增加连接耗尽警报功能。

客户无需重置密码，也无需重新上传已显示在账户中的文件。如果某次上传仍标记为“进行中”，请先确认其是否已完成，再决定是否重新发起；否则可能会导致文件重复。我们将根据客户合同，仅向符合条件的账户发放服务补偿。本通知旨在说明事件经过，不应被解读为我们承诺类似事件绝不会再次发生。
```

### long_zh_en · 长段中译英 · zh→en

原文：

```text
本次评审的重点不是把所有服务一次性迁移到新平台，而是确认最小范围的试点能否稳定运行。试点仅覆盖两个内部团队，不包含外部客户。现有合同、计费方式和数据保留期限均保持不变。如果试点未达到预期，我们将暂停扩大范围，但不会立即关闭已经上线的服务。

上线前，运维团队必须完成数据库备份，并验证备份确实可以恢复。测试环境通过回归测试并不意味着生产环境可以跳过检查。部署时先更新只读节点，再逐步切换写入流量；只有当错误率连续三十分钟低于百分之零点五，且延迟没有明显增加时，才能继续下一阶段。若迁移失败，只回滚本次数据库事务；若应用版本本身存在问题，则恢复上一版本并保留故障日志。

我们预计新方案可以减少约百分之二十的资源消耗，但这只是基于当前工作负载的估计，并非对所有场景的保证。业务增长可能抵消这部分节省。每个团队需要指定一位负责人，在周五之前提交监控指标、回退方案和联系人信息。没有提交材料的团队暂时不能进入试点。请不要把“默认启用”理解为“强制启用”：用户仍然可以在设置中关闭该功能，关闭后也不会丢失已有数据。
```

检查重点：完整三段；仅两个内部团队；暂停扩展不立即关闭服务；先备份验证恢复；只读节点先行；连续30分钟错误率低于0.5%；事务/版本回退不同；预计减少20%非保证；默认非强制。

**index-mt-2b**（首字 0.305s；完成 1.595s）

```text
The focus of this review is not to migrate all services to the new platform at once, but to confirm whether a minimal pilot can operate stably. The pilot will only cover two internal teams and will not include external customers. Existing contracts, billing methods, and data retention periods will remain unchanged. If the pilot does not meet expectations, we will pause expanding the scope, but we will not immediately shut down the services that are already live.

Before launch, the operations team must complete a database backup and verify that the backup can indeed be restored. The fact that the test environment passes regression tests does not mean the production environment can skip checks. During deployment, first update the read-only nodes, then gradually switch the write traffic. The next phase can only proceed when the error rate is below 0.5% for thirty consecutive minutes and there is no significant increase in latency. If the migration fails, only this database transaction will be rolled back. If there is an issue with the application version itself, revert to the previous version and retain the fault logs.

We anticipate that the new solution will reduce resource consumption by approximately 20%, but this is an estimate based on the current workload and not a guarantee for all scenarios. Business growth could offset this savings. Each team needs to designate a responsible person to submit monitoring metrics, rollback plans, and contact information by Friday. Teams that do not submit the required materials will not be eligible for the pilot for the time being. Please do not interpret "default enabled" as "forced enabled": users can still disable the feature in their settings, and existing data will not be lost if it is disabled.
```

**index-mt-9b**（首字 0.300s；完成 4.164s）

```text
The focus of this review is not on migrating all services to the new platform at once, but on confirming whether a minimal pilot can operate stably. The pilot will cover only two internal teams and will not include external customers. Existing contracts, billing methods, and data retention periods will remain unchanged. If the pilot does not meet expectations, we will pause further expansion but will not immediately shut down the services that have already gone live.

Before launch, the operations team must complete a database backup and verify that it can be successfully restored. Passing regression tests in the test environment does not mean that the production environment can skip its checks. During deployment, read-only nodes will be updated first, followed by a gradual switch of write traffic. The next phase may only proceed if the error rate remains below 0.5% for a continuous 30 minutes and latency does not increase significantly. If the migration fails, only the current database transaction will be rolled back. If the application version itself has issues, the previous version will be restored, and the failure logs will be retained.

We anticipate that the new solution will reduce resource consumption by approximately 20%, but this is merely an estimate based on current workloads and not a guarantee for all scenarios. Business growth may offset these savings. Each team must designate a lead to submit monitoring metrics, a rollback plan, and contact information by Friday. Teams that do not submit these materials will not be able to participate in the pilot for the time being. Please do not interpret “enabled by default” as “compulsory”: users will still be able to disable the feature in their settings, and doing so will not result in the loss of existing data.
```

**index-mt-35b**（首字 0.513s；完成 2.949s）

```text
The focus of this review is not to migrate all services to the new platform at once, but to confirm whether a minimal pilot can run stably. The pilot will only cover two internal teams and will not include external customers. Existing contracts, billing methods, and data retention periods will remain unchanged. If the pilot does not meet expectations, we will suspend further expansion but will not immediately shut down services that have already been launched.

Before going live, the operations team must complete database backups and verify that the backups can indeed be restored. Passing regression tests in the test environment does not mean that checks in the production environment can be skipped. During deployment, read-only nodes will be updated first, followed by a gradual switch of write traffic. The next stage can only proceed if the error rate remains below 0.5% for thirty consecutive minutes and latency shows no significant increase. If the migration fails, only the current database transaction will be rolled back; if the application version itself has issues, the previous version will be restored, and the failure logs will be retained.

We anticipate that the new solution will reduce resource consumption by approximately 20%, but this is merely an estimate based on current workloads and not a guarantee for all scenarios. Business growth may offset these savings. Each team must designate a lead to submit monitoring metrics, a rollback plan, and contact information by Friday. Teams that fail to submit the required materials will be temporarily excluded from the pilot. Please do not interpret "enabled by default" as "mandatory": users can still disable the feature in their settings, and doing so will not result in any loss of existing data.
```
