# 全局去重规则

## 目的

本规则负责判断新候选误区与历史正式卡片是否重复、相关或全新。它不仅处理同一篇文稿内部的重复，也处理跨文稿、跨批次的全局重复。

## 去重前提

去重比较对象不是标题或标签，而是候选的语义结构：

```text
错误对象 + 错误动作 + 错误判断 + 错误发生阶段
```

四项高度一致时，即使标题不同，也应优先判为重复。

## 四种判断结果

### duplicate

完全重复或核心误区重复。错误对象、错误动作、错误判断和发生阶段基本一致。

处理：不生成新正式卡，记录 `duplicateOf` 和判断理由。

### related

主题或因果链相关，但错误判断、对象或阶段不同，可以独立成卡。

处理：允许保留并生成新卡，在索引中记录 `relatedCardIds`；不能因为标签相同就合并。新卡落盘后，应把新卡的 `cardId` 同步加入相关 active 卡片的 `relatedCardIds`，保持关系双向一致。

### new

与历史卡片不存在本质相同的错误判断，允许进入生成、润色、审核和落盘流程。

### uncertain

证据或语义边界不足，无法判断重复关系。

处理：暂停该候选和整个批次，不擅自生成、跳过或删除；向用户展示最相近的历史卡，等待选择。

## 字段边界

- 卡片 Markdown YAML 使用 snake_case：`card_id`、`source_address`；
- `card-index.jsonl` 和 `processing-log.jsonl` 使用 camelCase：`cardId`、`sourceAddress`；
- 两种字段不能混用；校验时按所在文件的契约解析。

## 统一判断输出

每个候选必须输出并记录以下结构：

```json
{
  "candidate": "候选误区标题",
  "dedupStatus": "duplicate",
  "matchedCardId": "MISC-000003-01",
  "reason": "错误对象、错误动作和错误判断基本一致",
  "comparison": {
    "errorObject": "same",
    "errorAction": "same",
    "errorJudgment": "same",
    "errorStage": "same",
    "independent成立": false
  }
}
```

`dedupStatus` 只能是 `new`、`duplicate`、`related` 或 `uncertain`。`duplicate` 必须有 `matchedCardId`；`related` 必须有 `relatedCardIds`；`uncertain` 必须有 `matchedCardIds` 和暂停原因。

## 两阶段比较

为控制卡片规模增长后的耗时，先做索引粗筛，再做语义复核。粗筛只读取分类、标签、标题、观点关键词、错误对象、错误动作和错误阶段，默认取最相近的 3—10 张历史卡；它不能直接判定 `duplicate`。如果候选证据显示相似范围超过该数量，必须扩展复核范围。

### 第一阶段：快速筛选

从 `workspace.yaml` 指定的 `<record_root>/card-index.jsonl` 读取历史索引，先按 `category`、`tags`、标题和误区观点核心词、`errorObject`、`errorAction`、`errorStage` 筛选可能相似的卡片。这一阶段只负责缩小比较范围，不能直接决定重复。

### 第二阶段：语义复核

对筛选出的候选逐项回答：

1. 错误对象是否相同？
2. 错误动作是否相同？
3. 错误判断是否相同？
4. 错误发生阶段是否相同？
5. 纠偏方向是否相同？
6. 两张卡能否各自脱离对方成立？

前四项高度一致时判 `duplicate`；只有主题相近但错误判断、阶段或对象不同，判 `related`。

## 处理原则

- 不因标签相同而合并；
- 不因都属于同一分类而合并；
- 不因结果相似而合并，要比较错误判断本身；
- 上游错误与下游后果可以分别保留；
- 不同阶段的相似错误可以分别保留；
- 不自动删除历史卡片，也不自动覆盖已有卡片；
- 新文稿提供同一误区的更好证据时，标记为补充证据，等待用户决定是否合并。

## 落盘门禁

去重必须发生两次：候选识别后与历史索引比较，生成审核后与最新索引再次比较。同篇所有卡作为一个 run 提交；前一篇完成最终去重、一致性提交、索引更新和完成校验后，才能处理下一篇。不得在同篇多卡之间释放批次锁。

两次去重都必须先保存当前 run 的独立比较产物，再由机器计算产物哈希写入 `stageReceipts`。候选识别后记录 `global_deduplication_pre`，正式提交前记录 `global_deduplication_final`；缺少任意一次真实产物或回执，禁止正式提交、禁止 `completed`、禁止开始下一篇。去重结果必须包含实际比较的候选、索引快照哈希或明确的零候选理由，不能只写 `result: passed`。索引在两次检查之间发生变化时，重新读取、比较并更新最终产物；不能沿用旧结论。

最终去重回执至少包含：

```json
{
  "stage": "global_deduplication_final",
  "status": "completed",
  "evidence": {
    "indexVersionChecked": true,
    "newDuplicates": 0,
    "result": "passed"
  }
}
```

## 索引一致性与生命周期

索引文件为 `workspace.yaml` 指定的 `<record_root>/card-index.jsonl`。第一行必须是：

```json
{"recordType":"indexMeta","schemaVersion":1,"updatedAt":"2026-11-01T00:00:00+08:00"}
```

处理前必须检查索引可解析、卡片路径存在、`cardId` 唯一，并且 `category`、`tags`、`sourceAddress` 与卡片 frontmatter 一致。当前允许的分类为 `个人IP`、`创业搞钱` 和 `成长逆袭`；无法明确归类时允许为空字符串。任何检查失败，先停止当前 run 的去重与提交，保留原索引及错误证据；仅在核对正式卡片、生命周期和历史记录后，由受控恢复流程重建并再次校验索引。不能以不完整的卡片目录盲目覆盖索引。

每张卡必须有生命周期字段：

```json
{"status":"active","supersededBy":null}
```

确认合并时保留旧卡文件，将旧卡标记为 `superseded`，并写入 `supersededBy`；默认检索只使用 `active`，不删除旧文件。

生命周期状态固定为：

- `active`：正常参与去重和检索；
- `superseded`：已被另一张卡替代，保留文件但默认不参与检索；
- `archived`：用户明确要求归档，保留文件和索引记录，但默认不参与检索。

不得擅自把卡片标记为 `superseded` 或 `archived`；必须有用户确认或明确的处理记录。

---

抖音 / 视频号 / 小红书同名：姜来已来2046
本人微信：jianglai8883
唯一产品：本人24h会员答疑群（找懂的人问就是捷径）

---
