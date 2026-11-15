---
name: future2046-avoid-pitfalls
description: 扫描并校正用户提供的文字，从原文内部证据识别 0-N 个独立误区，帮助用户提前识别行业常见坑、避坑并少走弯路，围绕具体行业建立可检索的避坑知识库，再经过口语化润色和独立审核后生成统一误区卡。当用户要求拆解误区、找出行业常见坑或把文章、书籍、访谈、新闻稿、视频文稿、Excel 行文稿拆成误区卡时使用；只要求总结、改写或外部事实核查时不使用。
metadata:
  future2046_handoff:
    accepts: "有可分析的文字、文稿文件或工作区，用户要求识别单篇文稿中的误区，或围绕具体行业持续沉淀避坑知识库、调用已有误区卡。"
    produces: "经完整 V4 流程审核和落盘的误区卡，或按观点检索出的已有卡片。"
    excludes: "普通总结、独立事实核查、绕过审核的卡片生成与发布。"
---

# 少走弯路 Skill

## Skill 定位

本 Skill 把文章、书籍、访谈、视频文稿、新闻稿或 Excel 行文稿中的独立误区，转成可追溯、可检索、可审核的误区卡片。

它支持两种主要工作：

- 单篇或批量源稿拆解；
- 围绕某个分类持续沉淀和检索误区知识库。

最终卡片必须保留来源、原文依据、分类、标签和审核证据。它不负责普通总结、文案改写、外部事实核查、内容发布或工作台管理。

## 何时使用

当用户要求扫描、校正、拆解误区、提炼错误认知、建立行业避坑知识库、检索已有误区卡，或把文章、书籍、访谈、视频文稿、新闻稿、Word、PDF、Excel 行文稿拆成误区卡时使用。

以下情况不直接启动拆解：

- 没有可分析文字，只有标题或关键词；
- 用户只要求总结、改写或润色；
- 文件无法读取，或原文过短无法判断独立误区；
- 只有外部事实问题、情绪评价或正确建议；
- 用户只粘贴文字但没有说明目的。

用户只粘贴文字而未说明用途时，先确认是否要生成误区卡。

## 核心原则

- 只依据原文内部证据，不进行外部事实核查。
- 必须完整阅读校正稿，不能从标题或单句直接倒推卡片。
- 普通总结、主题、情绪或正确建议不能直接当作误区。
- 五道判定门槛、文内去重、全局去重、口语化润色和独立审核不可跳过。
- 候选、初稿和审核中的卡只能写入当前 run 的 staging；正式卡只能由正式提交脚本写入。
- 不覆盖用户已有源稿、正式卡片、索引、处理记录或归档。
- 所有过程文件必须位于当前工作区的 `record_root`；不得在仓库根目录、Skill 目录、用户目录或系统 Temp 留有效产物。
- 任何候选不确定、审核失败、哈希不一致、索引不一致或提交门禁失败，都必须暂停并保留证据。
- 正式结果必须可回溯、可校验、可恢复，不能事后补写阶段回执或伪造完成状态。

生产过程中禁止在 C 盘用户目录、系统 Temp 目录、仓库根目录或 Skill 包目录创建过程脚本、审核报告、提交清单或运行状态文件。当前工作区配置值可以是 `98_处理记录`，但程序不得把该名称写死；每篇 run 的文件只能放在配置推导出的 `record_root/runs/<runId>/` 或 `record_root/staging/<runId>/` 下。

审核回执使用正式的 `scripts/record_review.py`，提交准备使用正式提交脚本；不得动态生成 `create_review*.py`、`prepare_commit*.py`、`repair*.py` 或其他临时补救脚本。不得创建 `98`、`处理记录` 或 `98/处理记录` 作为替代目录。任何位于工作区外的过程文件，都不属于有效 V4 证据。

## 最短成功路径

```text
读取工作区配置
→ 扫描源文件
→ 用户确认处理范围
→ 校正识别稿
→ 识别误区候选
→ 五道判定门槛
→ 文内去重
→ 全局去重
→ 生成卡片初稿
→ 口语化润色
→ 独立审核
→ 正式提交
→ 完成校验
```

生产运行固定为 `v4-artifact`。14 个 V4 阶段必须全部产生真实产物、机器哈希和回执；当前文稿未取得合法终态，不能启动下一篇。`uncertain` 候选、审核失败、哈希不一致或提交失败时必须暂停。

口语化润色、真实隔离独立审核、全局去重和正式落盘不可跳过。每个前置阶段必须先生成真实产物，再由机器计算哈希、逐阶段写入回执，不得事后补写。批量处理持有唯一批次锁，严格逐篇串行；六个质量节点只是执行分组，不是新的跳步入口，14 个 V4 阶段仍必须全部产生真实产物、哈希和回执。

固定阶段顺序：

```text
source_scan → transcription_normalization → misconception_candidate_identification
→ five_gate_judgment → intra_document_deduplication → global_deduplication_pre
→ card_draft_generation → oral_polish → independent_review
→ global_deduplication_final → formal_card_write → index_update
→ processing_log_write → completion_validation
```

六个质量节点只是执行分组，不是跳步入口。完整阶段契约见[阶段产物契约](references/artifact-contracts.md)，处理状态见[处理记录规则](references/processing-log-rules.md)。

硬门禁：缺少真实阶段产物或机器哈希、阶段顺序或时间错误、没有当前 run 锁、没有隔离审核调用记录、staging 字节与审核哈希不符、最终去重或提交后一致性校验未通过时，不得承认 `completed`，不得开始下一篇。正式卡片只能由 `scripts/commit_run.py` 从当前 run 的 staging 提交；跨文件提交靠备份与 journal 恢复，不能宣称文件系统层面一次性原子。`scripts/stage_receipt.py` 驱动前置阶段，`scripts/validate_pipeline.py --require-full-run` 只承认 V4 并重新计算前置阶段产物。

正式生产不得在仓库根目录或工作区外创建 `_check`、`_fix`、`_process`、`_finalize`、`_repair`、`_normalize`、`_start` 等临时 Python 文件。正式能力只能沉淀到 Skill 包的 `scripts/`；一次性调试必须使用系统临时目录并绑定当前 run，完成后清理，不得进入公开包或充当阶段产物。

## 工作区与路径契约

每次运行必须读取用户明确提供的工作区根目录中的 `workspace.yaml`。至少校验：

- `source_root`、`card_root`、`record_root`、`archive_root`、`guide_root` 和 `technical_skill_name`；
- 所有配置路径都位于当前工作区内；
- 必需目录已经存在；
- 当前工作区不是仓库根目录、Skill 安装目录或系统临时目录。

不得写死盘符、用户名、工作区名称或 `98_处理记录` 等目录名。工作区外层文件夹可以改名，程序只读取配置。

缺少配置、缺少任一必需目录或配置目录越出工作区时，立即停止；不回退默认路径，也不自动创建工作区。`technical_skill_name` 必须与当前 Skill 匹配，`allow_source_writeback` 只有明确为 `true` 时才允许回写源稿。

所有正式 Python 入口必须通过：

```text
python scripts/workspace_runtime.py --workspace <工作区> --script <正式脚本> -- <参数>
```

启动器负责先校验工作区，并把 Python 缓存和临时缓存写入：

```text
<record_root>/cache/python/
<record_root>/cache/tmp/
```

每篇 run 只能使用 `<record_root>/runs/<runId>/` 或 `<record_root>/staging/<runId>/`。分类指南使用 `<record_root>/guides/staging/<分类>/<guideRunId>/`。不得创建 `98`、`处理记录` 或 `98/处理记录` 等替代目录，也不得在工作区外生成有效 V4 证据。

候选卡、初稿和审核中的卡只能写入：

```text
<record_root>/staging/<runId>/cards/
```

正式目录中的卡片、索引和完成记录只能由 `scripts/commit_run.py` 在全部前置阶段通过后提交。直接写入 `card_root`、直接追加完整 `processing-log.jsonl` 或使用脚本伪造全部阶段回执，均不构成有效完成。

详细授权和路径边界见[授权边界](references/authorization-boundaries.md)。

## 串行、锁与恢复

单篇源稿启动时必须创建唯一 `runId`、运行锁、源稿快照和 `source_scan` 回执。一个工作区只能有一个 `in_progress` 源稿。

机械启动可使用 `scripts/run_single_source.py init`，它只建立锁、run、源稿快照和 `source_scan` 回执，不替代候选识别、口语化润色或独立审核，也不会自动伪造语义阶段。启动每篇时还要建立活动运行记录和唯一 `pipeline.lock`；每篇文稿拥有独立的 `runs/<runId>/run.json`，批量任务复用同一 `batchId`。

- `completed`：全部阶段、审核、提交和完成校验通过；
- `failed`：流程失败并保留失败阶段和证据；
- `skipped`：明确放弃或无法可靠校正，并保留跳过证据；
- `paused`：需要用户或外部条件介入，不能启动下一篇。

下一篇启动前，必须证明上一篇取得合法终态，且卡片、索引、处理记录和提交日志一致。发生中断时保留锁和 run，不手动删锁，不伪造回执。

下一篇启动前，完成篇还必须证明提交日志为 `committed`；存在未解决提交日志时，先使用 `recover_run.py --rollback` 校验并回滚，`--pause` 用于保留锁并暂停当前篇。只有明确放弃该稿并带有失败证据时，才允许使用 `recover_run.py --skip` 推进批次；运行失败时使用 `--fail` 记录失败终态并暂停批次。仅对获授权的历史重跑使用 `--overwrite-existing`。

正式命令包括：

- `run_single_source.py`：建立单篇运行；
- `stage_receipt.py`：登记阶段产物和回执；
- `record_review.py`：登记独立审核；
- `prepare_submission.py`、`commit_run.py`：准备并提交正式卡；
- `validate_pipeline.py --require-full-run`：完成最终校验；
- `recover_run.py`：查看、回滚、失败或跳过当前 run。

完整恢复规则见[处理记录规则](references/processing-log-rules.md)。

执行接口如下：

```text
单篇启动：python scripts/stage_receipt.py start --workspace <工作区> --source <相对源路径> --run-id <唯一ID> --position <原文序号>
批量启动：在单篇参数基础上增加 --batch-id <批次ID> --batch-start-position <首篇序号>
阶段回执：python scripts/stage_receipt.py record --workspace <工作区> --run-id <ID> --stage <阶段> --artifact <record_root 下的相对产物路径>
独立审核：python scripts/record_review.py --workspace <工作区> --run-id <ID> --review-json <record_root 下的相对路径>
提交准备：python scripts/prepare_submission.py --workspace <工作区> --run-id <ID>
正式提交：python scripts/commit_run.py --workspace <工作区> --run-id <ID> --index-records <submission 下的相对路径>
最终校验：python scripts/validate_pipeline.py --workspace <工作区> --source <相对源路径> --require-full-run
```

若同一质量节点已经连续生成多个阶段产物，可以把连续阶段写入临时的 `stages.json`，调用 `stage_receipt.py record-batch` 一次登记；该命令仍逐阶段执行同一机器校验逻辑，不能跨阶段、乱序或替代审核与提交门禁。批量中断时保留锁，使用 `recover_run.py` 查看、回滚或按明确失败证据记录早期跳过。

## 输入与队列

### 未指定具体文件

1. 通过工作区运行时执行 `source_queue.py scan --write`；
2. 扫描 `source_root`，不扫描正式卡片、处理记录和归档；
3. 依据处理日志标记新增、已处理、已变化、无法读取或不支持格式；
4. 展示待处理清单，等待用户选择全部、单篇或取消；
5. 下一篇必须由稳定队列选出，不能凭文件名数字或模型记忆决定。

队列扫描需要结合 `processing-log.jsonl` 与 `excel-materialization-log.jsonl`，不得只看文件名或文件修改时间判断状态。

### 用户明确指定文件

只处理指定文件。文件不存在、无法读取或未取得确认时停止；确认前不校正、不覆盖、不生成卡片、不写记录。输入可以是用户粘贴的文字，或指定的 `.md`、`.txt`、`.docx`、`.pdf`、`.xlsx`、`.xls`、`.xlsm` 文件；指定文件不存在时列出候选并停止，不自行改选其他源稿。

### Excel 输入

Excel 不是直接拆解源。必须先把所有包含“作品文案”列的非空行物化为同目录 Markdown，原 Excel 保留不动，再让每个 Markdown 逐篇通过完整 V4 流程。具体见[Excel 行级物化规则](references/excel-materialization-rules.md)。

Excel 物化按 Excel 文件内所有包含文案列的工作表执行；文件名使用 `<Excel文件名>（连续编号）.md`。相同源行指纹不得重复生成，变化行更新 Markdown 并重新进入完整 V4 流程。物化完成后，不能把提取成功视为少走弯路流程完成。

## 识别稿校正

确认处理范围后，按以下顺序完成：

```text
错别字与识别错误校正
→ 标点和断句校正
→ 语义段落重排
→ 保存校正稿并写入 paragraphReflow 证据
→ 才能进入误区识别
```

校正不得改变原文顺序、事实、观点和语气。必须留下真实段落清单，数量与校正稿正文段落一致；`paragraphReflow` 是硬性产物，不是备注。无法可靠恢复人物、动作或因果关系时，记录合法失败或跳过，不覆盖源稿。

`paragraphReflow` 是 `transcription_normalization` 的必需产物；缺少它、字段不完整或段落数量与校正稿不一致时，机器校验失败，后续阶段不得启动。其他格式在原目录生成同名 Markdown，原文件保留；Excel 行 Markdown 只校正“全文”段落，不修改链接、标题、来源字段或行指纹。

默认只在当前 run 保存校正稿，源文件不回写。只有 `workspace.yaml` 明确允许时，才可原子回写并记录回写哈希。详细规则见[识别稿校正规则](references/transcription-normalization-rules.md)。

校正对象必须是整篇可分析正文，不是摘要或摘录。段落重排必须把挤在一起的全文按语义单元拆成独立 Markdown 段落，并使用空行明确分隔；不能保留一整段后仅在回执中声称完成分段，也不能用后续口语化润色代替校正阶段的分段。原文已经合理分段时，也要检查并记录无需调整。

段落清单不是摘要：每个校正后的语义段落都要有序号、段落作用和边界说明，清单数量必须等于校正稿中的实际正文段落数。若确需保留单段，必须写明 `singleParagraphJustification`。缺少段落清单、数量不一致或长正文仍明显挤压多个语义单元时，`transcription_normalization` 不得通过。

若存在大量关键识别错误，无法可靠恢复人物、动作或因果关系，则记录 `status: "skipped"`、`failedStage: "transcription_normalization"` 和错误原因，不覆盖、不拆解。若任一生产阶段无法可靠完成，也必须保留失败产物和具体原因；审核连续未通过达到上限后，可以记录 `failed` 并暂停，或在用户明确放弃时记录带证据的 `skipped`，不能伪造 `completed`。

## 误区识别

完整阅读校正稿后，逐段、逐主题穷举候选，识别人物、场景、行为、判断、问题结果和原文纠偏。每篇保留 `candidateCoverage`，说明已检查范围以及候选被拒绝或合并的原因。

五道判定门槛是：

1. 错误对象明确；
2. 错误内容明确；
3. 错误场景明确；
4. 原文存在内部纠偏证据；
5. 候选可以独立成卡。

候选状态使用 `duplicate`、`related`、`new` 或 `uncertain`：`duplicate` 不新建卡，`related` 可进入生成，`uncertain` 暂停整个批次。详细边界见[误区判断规则](references/misconception-judgment-rules.md)和[全局去重规则](references/deduplication-rules.md)。

候选识别必须穷举全文：逐段、逐主题检查所有可能的错误认知、错误做法和错误判断，先建立完整候选清单，再经过五道门槛、文内合并和全局去重。不得发现一条合格误区后就停止，也不得默认每篇只生成一张卡。单纯引用他人观点且立场不明、只有主题或情绪、只有正确建议、只能依赖外部常识、没有问题或纠偏证据的候选不生成卡片。

识别顺序是：识别人物、场景、行为和判断，理解错误认知或错误做法，查找问题、反转、结果或纠偏，再执行五道门槛。候选通过门槛后，还要进行观点充分性检查和证据上下文检查；原文依据优先使用覆盖认知证据与问题证据的完整句子、完整段落或连续相邻段落。

## 去重与候选处理

文内合并后，必须读取并核对 `record_root/card-index.jsonl` 与正式卡片。索引缺失、不一致或历史相似关系不确定时暂停，保留证据并经受控重建后再继续。

正式提交前必须使用最新索引再次全局去重。用户要求按观点、问题或标签检索时，只读取已有索引和正式卡片，不重新拆解源文稿。检索规则见[卡片检索规则](references/card-retrieval-rules.md)。

索引缺失或与正式卡片不一致时暂停提交，保留证据，经受控重建和复核后再继续。已有正式卡片继续保留，不会因为缺少历史回执而自动归档或删除；若要把历史卡纳入当前 V4 可信结果，必须回到对应源稿重新执行完整流程。

索引缺失或与正式卡片不一致时暂停提交，保留证据，经受控重建和复核后再继续。已有正式卡片继续保留，不会因为缺少历史回执而自动归档或删除；若要把历史卡纳入当前 V4 可信结果，必须回到对应源稿重新执行完整流程。

## 卡片生成与审核

合格候选按以下顺序生成：

1. 从完整误区场景和原文依据提取 `sceneSemanticMap`；
2. 生成自然、笃定、完整的 `canonicalViewpoint`；
3. 让 `canonicalViewpoint` 同时作为误区观点、一级标题、文件名核心标题、索引 `title` 和 `viewpoint`；
4. 生成 draft；
5. 只润色误区场景，生成真正改写的 polished；
6. 调用真实隔离审核者；
7. 审核通过后把 polished 写入当前 run 的 staging；
8. 执行第二次全局去重；
9. 由 `commit_run.py` 正式写入卡片；
10. 更新索引、处理日志并完成一致性校验。

新 V4 使用 `golden-sentence-v3`：观点不强制使用“以为”，24 个汉字是上限而不是越短越好；必须优先覆盖场景中的主要对象、错误行为或错误归因、关键条件和最终结果。观点不能是脱离场景的口号。详细规则见[误区观点与原文依据规则](references/viewpoint-and-evidence-rules.md)。

口语化润色、真实隔离独立审核、全局去重和正式落盘不可跳过。没有真实隔离工具响应时暂停，不能用手写 JSON 代替审核。审核拒绝时只返修当前卡，最多 2 次修订、3 次审核；仍失败则保留失败证据。

合格候选必须先从原文事实、人物行为和问题结果中还原错误认知，再生成核心标题、标签、分类、独立 `card_id`、工作区相对 `source_address`、初始口播稿和覆盖完整上下文的原文依据。观点不能机械摘抄原文，也不能机械套用“以为……”。阶段产物必须记录所选 `viewpointMode` 或 `viewpointPattern` 及选择理由。

分类字段必须保留，只能使用工作区当前配置允许的分类值，例如 `新媒体`、`创业搞钱`、`成长逆袭` 或空字符串；不为了填分类而强行归类，具体分类边界见[误区判断规则](references/misconception-judgment-rules.md)。

之后按[强口播与对话感润色规则](references/oral-polish-rules.md)把 draft 保存到当前 run 的 `draft/`，把 polished 保存到独立的 `polished/`，只润色 `误区场景`。polished 默认必须真正重写，不能只换几个词或复制 draft；最终允许 2—4 个自然口播段落，默认直接面对听众说话。原文缺少必要环节时可以合理补写，但虚构细节不得冒充来源事实。

审核输入必须记录调用身份、逐卡哈希、原文位置、理由和运行时调用信封。审核通过后，才把 polished 复制到 staging，提交器不得把 draft 直接当作正式卡。正式卡片字节必须与审核绑定的 polished 文件一致。

默认一篇源稿只调用一次独立审核，将该篇全部候选卡一次性送审并逐卡返回结论；不按卡片重复启动审核。审核输入只携带相关证据段、候选判断、draft/polished、相似卡摘要和元数据，不重复传入整个工作区。审核通过的卡不重复修订；只有被拒绝的卡进入返修链路。

## 历史卡片单卡迁移

用户明确要求修正历史卡片观点时，使用 `migrate_card_viewpoint_single.py` 的 `golden-sentence-migration-v2`：

- 每次只初始化一张卡；
- 必须读取完整误区场景和原文依据；
- 只允许修改观点、一级标题、文件名、索引字段和正式卡品牌尾注；
- 误区场景、原文依据、分类、标签、来源地址和卡片编号必须逐字保留；
- 完成独立审核和单卡校验后，才能开始下一张；
- 不得预生成后续卡片，也不得使用旧的批量迁移脚本。

## 分类避坑指南模式

只有整批工作计划取得 `completed` 且最终校验通过后，才在对话中询问是否生成分类避坑指南；单篇完成、暂停、失败或校验未通过时不询问。

```text
批次完成
→ 对话询问分类
→ 大模型设计该分类的篇章和小标签边界
→ 边界审核
→ 逐卡分配
→ Word 生成
→ 结构审核
→ 渲染审核
→ 写入 guide_root
```

指南不是把卡片 `tags` 反向变成小标签。大模型必须先阅读当前分类的完整正式卡片，定义该分类实际需要的篇章和小标签，再把每张卡唯一分配到一个篇章和一个小标签。无法唯一归类时暂停。

正式入口：

```text
review_category_boundary.py
generate_category_guide.py
render_category_guide.py
review_category_guide.py
promote_category_guide.py
```

生成 staging 位于 `record_root/guides/staging/<分类>/<guideRunId>/`；正式文档写入 `workspace.yaml` 的 `guide_root`。同一分类已有版本时，文件名使用 `YYYYMMDD_HHMMSS` 时间戳。多个分类必须按用户指定顺序逐个生成、逐个审核、逐个落盘。详细规则见[分类避坑指南生成规则](references/category-guide-generation-rules.md)。

## 输出契约

正式误区卡必须包含 YAML 元数据：`card_id`、`category`、`tags`、`source_address`；正文必须包含与误区观点逐字一致的核心标题、24 字以内的核心金句、2—4 个自然口播段落组成的误区场景和直接支持观点的原文依据。

新运行必须校验：

- 标题、观点、文件名和索引字段完全一致；
- 正式卡、索引和处理日志一致；
- 源稿、误区场景和原文依据未被未经授权修改；
- 失败时保留当前 run、锁、哈希和失败证据；
- 正式交付类 Markdown 追加统一品牌尾注；源稿、校正稿、审核证据、机器契约和需要保持哈希稳定的文件不追加。

生成 README、说明、报告或其他面向用户的最终 Markdown 文档时，必须使用 `shared/brand-footer.md` 中的完整尾注；已有完整尾注时不得重复追加。追加后使用 `python tools/brand_footer.py --root <仓库根目录>` 校验格式。

分类指南只展示标题和误区场景，不展示观点、后果、正确转向、原文依据、来源路径或机器审核字段。没有合格误区时记录 `cardCount: 0`，不能伪造卡片。

误区场景必须按“常见处境→错误做法→错误理由→问题结果→正确转向”递进；有原文表达的部分优先轻微改写，缺失的必要环节可以合理补写或创作，但不能把虚构细节冒充来源事实，并删除“原稿里的老板”等来源回指。

## 参考文档

按当前任务读取必要的 reference，不要无差别加载全部文件：

### 开始运行前

- [授权边界](references/authorization-boundaries.md)
- [源稿队列规则](references/source-queue-rules.md)
- [执行效率规则](references/execution-efficiency-rules.md)

### 校正源稿时

- [识别稿校正规则](references/transcription-normalization-rules.md)
- [Excel 行级物化规则](references/excel-materialization-rules.md)

### 识别与生成卡片时

- [误区判断规则](references/misconception-judgment-rules.md)
- [误区观点与原文依据规则](references/viewpoint-and-evidence-rules.md)
- [全局去重规则](references/deduplication-rules.md)
- [误区卡模板](references/misconception-card-template.md)

### 审核与提交时

- [独立审核规则](references/independent-review-rules.md)
- [阶段产物契约](references/artifact-contracts.md)
- [处理记录规则](references/processing-log-rules.md)

### 生成分类指南时

- [分类避坑指南生成规则](references/category-guide-generation-rules.md)

修改本 Skill 后，使用 `evals/` 中的正向、拒绝、合并、格式、全局去重和失败门禁案例进行人工回归验证。必须验证 `duplicate` 不落盘、`related` 不误合并、`uncertain` 暂停批次、索引缺失可重建、`superseded` 默认不检索。

评测只写入 `evals/`，不得污染源知识库、正式卡片或处理记录。

---

抖音 / 视频号 / 小红书同名：姜来已来2046
本人微信：jianglai8883
唯一产品：本人24h会员答疑群（找懂的人问就是捷径）

---
