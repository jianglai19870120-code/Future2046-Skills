# v4 处理记录与串行提交规则

正式记录位于 `workspace.yaml` 指定的 `<record_root>/processing-log.jsonl`，一篇源稿一个 `runId`，`pipelineVersion` 固定为 `v4-artifact`。记录追加写入，不改写当前 V4 记录。

## 生产路径锁定

所有运行产物、审核证据、提交清单、恢复文件和阶段回执必须位于当前工作区配置的
`record_root`。生产脚本不得写入 `C:\Users\`、系统 Temp、仓库根目录或 Skill 包目录；
不得动态生成临时 Python 补救脚本。审核响应通过 `scripts/record_review.py` 写入当前
run 的 `review/`，提交输入通过 `scripts/prepare_submission.py` 校验当前 run 的
`submission/`。工作区外文件即使内容正确，也不能作为 V4 证据。

历史卡片索引重建、迁移和清理说明不属于源稿处理记录，统一写入 `98_处理记录/recovery-events.jsonl`。不得把 `historical_rebuild`、`reconstructed` 或其他非 V4 记录写入正式 `processing-log.jsonl`，也不得据此宣称源稿已完成 V4 流程。

Excel 物化另写入 `98_处理记录/excel-materialization-log.jsonl`。每条记录必须包含 `sourceExcel`、`sheet`、`sourceRow`、`generatedPath`、`rowFingerprint`、`sourceExcelSha256` 和 `status`。`status` 可为 `materialized`、`changed`、`unchanged`、`empty_text`、`unsupported_sheet`、`conflict` 或 `failed`。只有 `materialized`、`changed` 和 `unchanged` 且目标 Markdown 存在时，才可进入源稿扫描；Excel 本身不作为误区拆解源稿。

Excel 生成的 Markdown 进入 V4 后，正式 `processing-log.jsonl` 还必须记录 `sourceKind: "excel_row"`、稳定的 `sourceIdentity`（行指纹）、`sourceExcel`、`sourceSheet`、`sourceRow` 和分配的 `queuePosition`。串行门禁以 `queuePosition` 为准，不得根据文件名中的数字推断顺序；传统 `经纬 (N).md` 记录继续使用既有 `sourceSequence` 兼容。

## 唯一运行与阶段回执

执行元数据可以记录：

```json
{
  "executionProfile": "bundled-v1",
  "qualityNodes": [
    "normalization",
    "candidate_and_gates",
    "dedup_pre",
    "draft_and_oral_polish",
    "independent_review",
    "commit_and_validation"
  ]
}
```

该字段只描述执行分组，不替代 14 个阶段回执，也不能作为跳过阶段的依据。

批次持有唯一 `98_处理记录/pipeline.lock`；`active-run.json` 只能指向一篇 `in_progress` 源稿，状态保存在 `runs/<runId>/run.json`。前一篇没有达到可信终态、存在活动锁或未解决提交日志时，不得启动下一篇。零卡稿也须完成适用的真实阶段、零卡审核和提交校验。

前置阶段依次为 `source_scan → transcription_normalization → misconception_candidate_identification → five_gate_judgment → intra_document_deduplication → global_deduplication_pre → card_draft_generation → oral_polish → independent_review → global_deduplication_final`。每次只提交当前阶段一张回执。回执包含 `stage`、`status`、严格递增的 `startedAt`/`completedAt`，以及由机器核验的 `artifactPath`、`artifactSha256`、`inputSha256`、`outputSha256`。产物内容和字段见[阶段产物契约](artifact-contracts.md)。不能先写回执、批量补造回执或仅凭运行时间声称执行成功。

后置阶段 `formal_card_write → index_update → processing_log_write → completion_validation` 由提交器写入。`status: completed` 仅在全部前置产物、隔离审核、最新索引去重、staging 卡片和提交后一致性校验通过后成立。最终记录须包含 `runId`、`sourceSequence`、`stageReceipts`、`cardCount`、`cardPaths`、`cardDetails`、`reviewStatus`、`reviewMode`、`reviewAttempts`、`processedAt`；卡片字段使用 camelCase，对应卡片 frontmatter 的 snake_case。失败或跳过记录保留实际截止阶段、`failedStage` 和 `error`，不得补造后续成功阶段。

## 可恢复的一致性提交

候选卡和润色卡保留在当前 run 的 staging 中。提交前冻结已审核的 polished 字节，重算哈希并核对 staging、目标文件名、索引记录及正式目录现状。`commit_run.py` 独占锁，先准备旧卡、索引、日志和 run 的备份及 `commit-journal.json`，再依次写正式卡、索引、完成记录和校验结果。这里的“原子提交”指**对外只承认通过最终校验且 journal 为 `committed` 的整次提交**；跨多个文件的写入不是单一文件系统事务，可能在中途留下部分新文件。

提交失败或进程中断时，保留锁、active run、staging、备份和 journal；不得手工标记 `completed`、释放锁、启动下一篇或再次盲目提交。先按 journal 核对各文件实际哈希与备份，再调用 `recover_run.py --rollback` 恢复旧卡、索引、日志和 run；如发现外部改动则保持阻塞并报告。回滚完成后当前 run 仍持有锁，可以修复产物后重试。早期无法可靠校正时，`recover_run.py --skip --failed-stage transcription_normalization --reason ...` 会记录跳过并释放锁。

## 审核与终态

独立审核的 `reviewMode` 只可为 `subagent` 或 `fresh_context`，且必须有隔离调用 ID、审核者 ID、审核工具、逐卡哈希与理由。生产者自审或仅写 `reviewEvidence: passed` 无效。零卡也要有 `zeroCardReason`。连续审核失败、校正无法可靠完成时可在实际失败阶段结束并记录 `failed` 或 `skipped`；去重 `uncertain`、索引不一致和部分提交属于一致性阻塞，须暂停整个批次，等待处理，不能将当前篇视为可越过的终态。

扫描源文件时，用最近一次可信成功记录的 `correctedSha256` 与当前文件哈希比较；没有顶层字段时，从 `transcription_normalization` 回执的机器计算 `outputSha256` 读取。失败记录不使文件变成已处理。Excel 行指纹变化会使对应 Markdown 重新进入 V4，不得沿用旧卡结果。`validate_pipeline.py --require-full-run` 只接受 `v4-artifact`，并重算阶段产物、提交器最终校验和 journal 的 `committed` 状态。

---

抖音 / 视频号 / 小红书同名：姜来已来2046
本人微信：jianglai8883
唯一产品：本人24h会员答疑群（找懂的人问就是捷径）

---
