# v4 阶段产物契约

`pipelineVersion` 固定为 `v4-artifact`。一篇源稿对应一个 run；阶段产物先于回执生成，且必须位于 `workspace.yaml` 指定的 `<record_root>/runs/<runId>/`。路径采用工作区相对 POSIX 格式，不允许越界。每个产物是独立 JSON 对象，至少包含 `runId`、`sourcePath`、`stage`；除 `source_scan` 外，还须包含与上一阶段机器计算输出哈希一致的 `inputSha256`。不能用同一份通用 JSON 或旧卡复制件冒充不同阶段的产物。

本契约约束的源稿、校正稿、审核证据和阶段产物不得追加品牌尾注，因为它们需要保持原文、字段和哈希稳定。面向用户的最终 Markdown 说明或报告不属于 V4 阶段产物；此类文档必须按 `SKILL.md` 的品牌尾注规则处理。

## 生产路径契约

所有 V4 过程文件必须位于 `workspace.yaml` 指定的 `record_root`。运行证据只能写入 `<record_root>/runs/<runId>/`，其中审核文件位于 `review/`，提交准备文件位于 `submission/`。卡片正式输出只能写入 `card_root`。默认 `allow_source_writeback: false`，校正稿保存在当前 run 内并作为后续输入；只有工作区明确开启写回时，才允许原子覆盖源文件。C 盘用户目录、系统 Temp、仓库根目录和 Skill 包目录中的文件不属于有效生产证据；生产脚本不得使用系统临时目录，也不得动态生成补救 Python 脚本。

Excel 物化是源稿进入 V4 前的预处理，不替代 V4 阶段。物化报告和 `excel-materialization-log.jsonl` 必须绑定 `sourceKind: "excel_row"`、`sourceIdentity`、`sourceExcel`、`sourceSheet`、`sourceRow` 和 `rowFingerprint`；物化失败不得生成源稿或误区卡。

`stage_receipt.py` 按当前文件字节计算大写 SHA-256，记录 `artifactPath`、`artifactSha256`、`inputSha256`、`outputSha256`。操作者提供的哈希只是待核对声明，不是计算结果；提交前重算源文件、引用文件和阶段产物的哈希。文件内容变化后，旧回执和所有依赖它的下游阶段失效，须从变化阶段重新执行。单纯时间戳、布尔 `passed` 或说明文字不能代替实际产物。

| 阶段 | 必须保留的真实产物 |
| --- | --- |
| `source_scan` | 源文件快照及其路径、原始文件哈希；建立回执时快照字节必须与源文件一致，提交前再次确认源文件未变化。 |
| `transcription_normalization` | 当前 run 的校正后 Markdown、逐项变更清单和必需的语义分段记录 `paragraphReflow`；默认不覆盖源文件，写回仅在工作区 `allow_source_writeback: true` 时启用。长单段正文必须完成真实分段，或留下明确的单段保留理由。 |
| `misconception_candidate_identification` | 候选列表、唯一候选 ID、错误认知、认知与问题的原文片段及位置；每个候选还要有 `viewpointPattern`、`patternSelectionReason`；`candidateCoverage` 必须证明全文所有语义段落和主题都已扫描，零候选需说明。 |
| `five_gate_judgment` | 覆盖全部候选的五门逐项布尔判断和理由，并绑定候选产物。 |
| `intra_document_deduplication` | 同篇候选的逐项比较、合并映射及保留集合，绑定五门产物。 |
| `global_deduplication_pre` | 索引字节哈希、每个保留候选的比较对象和 `dedupStatus`；零候选给出明确理由。 |
| `card_draft_generation` | 新生成的每张 draft 卡及清单、机器核对的文件哈希；`generatedFrom` 为 `source_and_candidates`。draft 必须放在当前 run 的独立 `draft/` 目录，不能写入 staging；旧正式卡只可只读参考。 |
| `oral_polish` | 每张 draft 与独立 polished 文件、两者哈希和改动说明；默认必须真实重写，未改动须写明理由并由独立审核批准。新增 `oralPolishQuality`：`changed`、`directAddress`、`dialogueFeeling`、`naturalConnectors`、`sentenceRhythmVaried`、`reportToneRemoved`、`paragraphCount`。只能改变 `误区场景`。 |
| `independent_review` | 冻结审核请求 `reviewRequestPath`、真实工具响应 `reviewerTranscriptPath`、调用 ID、审核者身份、每张 polished 卡的哈希、逐卡决定、理由和原文证据位置；零卡须写审核理由。 |
| `global_deduplication_final` | 提交前最新索引哈希、逐候选复核和 `result: passed`；索引变化则重新比较。 |
| `formal_card_write` 至 `completion_validation` | 由提交器产生的正式卡写入清单、索引哈希、日志写入证据和最终一致性校验结果。不得手工补造。 |

审核报告必须绑定实际被审核的 polished 文件哈希。polished 必须放在当前 run 的独立 `polished/` 目录；审核通过后，提交器才把 polished 复制到 staging，staging 只保存待提交的最终 polished 字节，且必须与审核哈希逐字节相同。`uncertain`、索引不一致、哈希不符、审核来源无法证明隔离或缺少产物时停止提交并保留现场。

`dialogue-v2` 口播契约要求：有卡文稿的 polished 场景默认与 draft 不同，且为 2—4 个自然段；审核报告还必须包含 `oralSceneEvidence`，证明直接面向听众、具有对话感、自然连接、长短句节奏、已去除报告腔且确实完成重写。

## 观点与证据字段

每个合格候选或卡片草稿必须保留：

```json
{
  "viewpointQuality": {
    "isMistakenBelief": true,
    "hasErrorObject": true,
    "hasErrorJudgment": true,
    "hasCausalDirection": true,
    "semanticComplete": true,
    "sourceClose": true,
    "tooCompressed": false,
    "isCorrectionConclusion": false,
    "sentenceCount": 1,
    "commaCount": 0,
    "characterCount": 18
  },
  "sourceEvidence": {
    "paragraphIds": [6, 7],
    "startSentence": 1,
    "endSentence": 5,
    "roles": {"cognitive": true, "problem": true, "correction": true},
    "isContinuous": true,
    "contextComplete": true
  }
}
```

`sourceEvidence` 的段落和句子范围必须能回到校正稿正文；新 V4 run 还必须提供 `evidenceSpans`，记录认知证据与问题证据的字符起止位置，机器会逐字核对、检查顺序和重叠。`isContinuous` 和 `contextComplete` 任一为 `false` 时不得审核通过。没有合格误区时仍需保留零候选理由，不得伪造观点或证据字段。

---

抖音 / 视频号 / 小红书同名：姜来已来2046
本人微信：jianglai8883
唯一产品：本人24h会员答疑群（找懂的人问就是捷径）

---
