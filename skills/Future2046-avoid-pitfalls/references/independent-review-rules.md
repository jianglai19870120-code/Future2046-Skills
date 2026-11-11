# 独立审核规则

## 目录

- [审核时点与独立性](#审核时点与独立性)
- [必检项](#必检项)
- [通过、退回与停止](#通过退回与停止)

## 审核时点与独立性

默认按“每篇源稿一次审核调用”提交该篇全部候选卡，审核器仍必须逐卡返回结论。不要为同一篇中的每张卡重复启动审核上下文。审核请求只保留校正稿相关证据段、候选和五道门槛、draft/polished、相似卡摘要以及元数据；无关源稿和全部历史卡正文不进入请求。审核失败时只返修被拒绝卡，已通过卡不重复处理。

口语化润色完成后、正式提交前，所有待提交卡必须接受真实隔离审核。优先调用独立子 Agent；不可用时只可调用具备隔离上下文的新审核执行器。新开一段对话、自称“独立审核”或由生产者切换角色复核，均不构成独立审核。审核者不得接收生成推理或预设的通过结论。分别记录 `reviewMode: "subagent"` 或 `reviewMode: "fresh_context"`；没有可用隔离工具时暂停，不能降级为自审。零卡稿同样由隔离审核者核对无卡理由。

审核输入是校正后原文、候选与五门判定、draft/polished 卡、去重结果和文件命名信息。审核者不改写卡片，逐卡给出 `approved` 或 `rejected`、具体理由及支持该判断的原文位置；拒绝时列出可执行原因。审核报告必须记录实际调用的 `reviewTool`、`reviewerInvocationId`、与 `producerId` 不同的 `reviewerId`，逐卡 `polishedPath` 与机器核对的 `reviewedCardSha256`。哈希或身份无法复核时不得放行。

审核调用的工具响应需原样保存在当前 run 的 `reviewerTranscriptPath`；审核报告必须和该响应的逐卡结论、哈希及理由一致，并绑定冻结的 `reviewRequestPath`。本地 JSON 文件及其哈希只能证明内容一致，无法独自证明工具调用确实发生；操作者必须实际调用隔离工具，并把真实调用 ID 连同原始响应留存。没有可核验的工具响应时停在审核阶段。

原始响应必须包含运行时调用信封，至少包括：

```json
{
  "invocation": {
    "id": "真实调用ID",
    "tool": "multi_agent_v1",
    "requestSha256": "冻结审核请求的哈希",
    "responseSha256": "响应对象的哈希",
    "startedAt": "调用开始时间",
    "completedAt": "调用完成时间"
  }
}
```

阶段校验器会核对调用 ID、工具名、审核请求哈希、响应哈希和时间字段。这个信封能防止把一份脱离当前 run 的普通 JSON 报告冒充审核响应，但不能替代真实隔离工具本身的调用；没有真实工具响应时仍必须暂停。

审核回执不是一句“通过”。通过时必须保存：

```json
{
  "reviewStatus": "approved",
  "reviewMode": "fresh_context",
  "reviewAttempts": 1,
  "reviewEvidence": {
    "fiveGateJudgment": "passed",
    "viewpointIsMistakenBelief": true,
    "sourceEvidenceSupportsViewpoint": true,
    "oralSceneIsNatural": true,
    "creativeDetailsDoNotConflict": true,
    "duplicateCheckPassed": true,
    "metadataCheckPassed": true,
    "filenameCheckPassed": true
  }
}
```

上面的检查项只是审核结论摘要，不是隔离调用证据。审核者的原始逐卡报告先保存为当前 run 的真实阶段产物，再由 `stage_receipt.py` 绑定机器计算哈希；不能事后补齐审核字段。审核后 polished 或 staging 字节变化，必须重新审核。零卡报告须有 `zeroCardReason`。

## 必检项

审核先检查[误区判断规则](misconception-judgment-rules.md)中的误区判定链，再检查卡片表达：

审核必须确认候选阶段覆盖了校正稿全文，而不是生成第一张合格卡后停止；被淘汰或合并的候选有记录；误区观点的句式与错误关系匹配，没有机械套用“以为……”。观点必须保留原文支持的错误机制，而不是只抄一句原话或改成纠偏结论。缺少 `candidateCoverage`、`viewpointPattern` 或 `patternSelectionReason` 时，审核应退回。

观点和原文依据还必须按[误区观点与原文依据规则](viewpoint-and-evidence-rules.md)复核：观点不能因追求短而丢失犯错对象或因果方向，原文依据必须是最小完整上下文，而不是关键词或断裂片段。

1. [误区判断规则](misconception-judgment-rules.md)中的五道门槛和立场识别是否全部通过；
2. 误区观点是否写的是犯错者相信的错误判断，且为单句、自然口语化、不超过24个汉字；
3. 标签是否有1-3个有效、非重复的语义标签；
4. 口播是否自然、笃定、有真人表达感，并按“常见处境→错误做法→错误理由→问题结果→正确转向”形成信息递进；
5. 创作内容是否未与原文核心事实、方向和判断冲突，且未冒充原文事实；
6. 原文依据是否直接覆盖认知证据和问题证据；
7. 标题、标签、正文与文件名是否一致；
8. 多卡时是否存在重复卡或遗漏明显误区。
9. YAML frontmatter 是否同时包含 `card_id`、`category`、`tags`、`source_address`；
10. `card_id` 是否唯一，`category` 是否允许为空但不能缺失，`tags` 是否为 1-3 项数组；
10a. `category` 是否只使用 `个人IP`、`创业搞钱`、`成长逆袭` 或空字符串，且与误区主要主题匹配；
11. 标签、编号和文件地址是否已从一级标题移入元数据，`source_address` 是否为工作区相对路径；
12. 文件名是否默认采用 `<原文稿名>_<核心标题>.md`，且与一级标题核心标题一致。
13. 是否删除“原稿里的老板”“源稿中的老板”“作者提到”“受访者后来”等来源回指和分析报告式表达；
14. 五个环节是否各自提供新信息，是否存在把同一个结论重复说五遍的情况；
15. 原文已有对应表达的环节是否保留了原文核心词语、事实、行为和判断，是否存在没有必要的过度改写；
16. 原文没有对应表达的环节，补写或创作是否服务于当前误区，且没有改变原文核心方向、事实结果或纠偏逻辑；
16a. 校正稿是否完成了必要的语义分段，且分段没有改变原文顺序、观点、事实和语气；
17. 创作的人物、场景、数字、细节和结论是否没有被包装成原文、作者或受访者明确说过的事实；
18. 正式落盘前是否已与 `card-index.jsonl` 完成第二次全局去重，且没有把 `duplicate` 候选写成新卡；
19. 如果判为 `related`，是否确实存在不同的错误对象、错误判断或错误阶段，而不是仅仅换了说法。
20. 去重结果是否包含统一的 `dedupStatus`、匹配卡片、比较结果和判断理由；
21. `uncertain` 是否暂停整个批次，`duplicate` 是否未写入正式卡片；
22. `card-index.jsonl` 是否存在、可解析，并与卡片 frontmatter 和卡片路径一致；
23. 卡片生命周期是否正确，默认检索是否排除 `superseded` 和 `archived`。
24. 观点是否充分表达原文中的错误意思，是否仍是犯错者相信的判断，而不是主题、标签或纠偏结论。
24a. 观点是否完成了“原文事实/人物原话→行为与理由→可复用错误认知”的还原，而不是机械摘抄人物的一句话；如果使用“很多人”等泛化主体，原文是否足以支持这种泛化。
25. 观点是否保留原文核心词和因果方向，是否单句、笃定、通常不超过一个逗号，且没有因过度压缩而失去语义。
26. `viewpointQuality` 是否完整，且 `isMistakenBelief`、`semanticComplete`、`sourceClose` 均为 `true`，`tooCompressed`、`isCorrectionConclusion` 均为 `false`。
27. 原文依据是否连续，至少覆盖 `cognitive` 与 `problem` 证据，必要时覆盖 `correction`；是否存在关键词拼接、远距离拼接、截断句子或截断因果关系。
28. `sourceEvidence` 是否包含段落范围、起止句、证据角色、`isContinuous: true` 和 `contextComplete: true`。
29. 对 `dialogue-v2` 运行，polished 是否真正重写而不是复制、换词或只改标点；是否直接面对听众，具有自然对话推进、长短句节奏和 2—4 个自然段。
30. 审核报告是否包含：

```json
{
  "oralSceneEvidence": {
    "directAddress": true,
    "dialogueFeeling": true,
    "naturalConnectors": true,
    "sentenceRhythmVaried": true,
    "reportToneRemoved": true,
    "meaningPreserved": true,
    "actualRewriteCompleted": true
  }
}
```

如果 polished 与 draft 相同，只有在审核者明确写出“不改写”的理由并确认原稿已经是成熟口播稿时才能放行；普通复制直接退回。

如果判断规则中的门槛或立场识别不通过，即使口播写得自然，也必须拒绝落盘。口播中的创作内容不能反过来弥补原文证据不足。

如果观点虽然不超过 24 字但语义不完整，或原文依据过短、无法让读者独立理解认知与问题关系，也必须退回。具体判断不得用卡片中新增的创作细节替代原文证据。

如果观点只是原文人物的一句自我宣言，虽然字面贴近原文，但没有表达背后的错误机制，也必须退回重写。审核应优先判断“读者能否从观点中看出错误方向”，而不是“观点是否在原文中逐字出现”。

## 通过、退回与停止

合理的创作细节本身不是退回理由；仅当创作内容与原文冲突、歪曲误区或冒充原文事实时退回。退回后执行“修订 → 口语化润色 → 再审核”。最多 2 次修订、3 次审核。

第三次审核仍未通过，禁止正式落盘：保留实际审核报告，记录 `failedStage: "independent_review"` 和失败原因，按恢复流程结束当前篇。隔离审核工具不可用或审核证据缺失时，暂停批次，不能把失败写成审核通过。通过后仍须完成最终去重和一致性提交，才能记录 `completed`。

---

抖音 / 视频号 / 小红书同名：姜来已来2046
本人微信：jianglai8883
唯一产品：本人24h会员答疑群（找懂的人问就是捷径）

---
