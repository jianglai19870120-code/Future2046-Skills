---
name: future2046-viral-root
description: 对标注账号作品标题，按八大爆款元素提出词根，经独立审核后计算热度并同步词典、汇总和明细。
metadata:
  future2046_handoff:
    accepts: "已配置爆款词根工作区；用户要求分析标题或同步账号作品数据。"
    produces: "经审核的词根词典、热度汇总、分类明细、审核记录和同步快照。"
    excludes: "不修改源 Excel，不把工作区数据写入 Skill 发布包。"
---

# 爆款词根 Skill

## 工作流程

本 Skill 把表格读取、标题语义审核、热度计算和文件同步分成明确步骤。脚本不自行推断标题含义；只有经过独立审核的“作品—词根”关系才会进入正式结果。

1. **确认工作区**：读取指定工作区的 `workspace.yaml`，核对输入、输出、处理记录、归档路径及八个已存在的编号目录。
2. **读取与预检**：扫描 `01_对标账号` 中的 `.xls`、`.xlsx` 和 `.xlsm`。旧 `.xls` 使用 Windows Excel COM 只读读取；其他格式使用 openpyxl。识别标题、点赞、评论、收藏、分享和可选链接列。
3. **清理与筛选**：标题截取第一个 `#` 或 `＃` 之前的正文。同账号内清理后完全相同的标题只保留点赞最高的行；最高点赞并列时全部保留。源 Excel 不变。
4. **按账号建立十条批次**：首次指定账号时运行 `review_batches.py prepare --new-run --first-account "李守洲"`，然后只用 `review_batches.py current` 获取当前解锁的十条。系统先按指定首账号、再按其他账号、源文件和行号排序；后续批次仅作为内部队列保存。当前批次未完成时，不得读取、拆解或提交下一批。每批必须包含恰好十个标题，最后一批可以少于十条。
5. **逐题初审与独立复核**：只处理当前解锁账号的当前批次。每条标题先写语义概括，再对八大元素逐项写“成立 / 不成立”和理由，然后提出 0–N 个标准词根。每个词根必须写提炼说明、元素理由、原文证据数组和独立审核四项检查；标准词根可以是标题多个片段的语义组合，但不得加入标题没有表达的信息。第二个独立 AI 逐项复核标准词根忠实度、证据逐字性、元素归属和理由支持度。没有词根的标题也必须保存完整八类排查和排除理由。审核结果通过 `review_batches.py commit` 落盘后，程序才解锁下一批；程序拒绝跳过未提交的前一批。驳回项保留在批次记录中，有争议项阻止该批提交。
6. **账号完成即同步**：当前账号的最后一批提交后，必须先运行 `review_batches.py sync-account --workspace <工作区> --account <账号>`，生成截至该账号的累计正式词典、汇总表、词根明细、快照和同步报告。同步成功后，再运行 `review_batches.py confirm-account --workspace <工作区> --account <账号> --sync-account`，程序才解锁下一个账号。也可以直接用带 `--sync-account` 的 `confirm-account` 完成“同步并解锁”；同步失败时状态保持等待，不得进入下一个账号。全部账号完成后仍可运行 `finalize` 做最终一致性重建。
7. **历史“最差”复查优先**：发现旧版“最差”关系需要迁移时，先运行 `prepare-worst-recheck` 建立按账号、每批十条选题的复查队列。复查期间 `current` 和 `commit` 被锁定；每批使用 `current-worst`、`commit-worst-recheck` 完成独立复核并落盘。全部复查批次完成且没有争议后运行 `finalize-worst-recheck`，程序才会备份并重建正式产物，然后恢复原普通队列。
8. **严格最差复核**：当“最差”规则从失败结果收紧为极端词白名单时，运行 `prepare-strict-worst-recheck`。该流程只复核当前正式“最差”关系，要求 `worst_trigger` 完整命中白名单；复核期间锁定普通队列，完成后运行 `finalize-strict-worst-recheck` 重建正式产物并恢复原批次。

## 运行命令

将 `<Skill目录>` 替换为本机实际安装目录，将 `<工作区>` 替换为目标工作区绝对路径。审核 JSON 保存到工作区的 `98_处理记录` 中。

```powershell
python "<Skill目录>\scripts\sync_viral_roots.py" --workspace "<工作区>" --reviews "<工作区>\98_处理记录\本轮审核.json" --dry-run
python "<Skill目录>\scripts\sync_viral_roots.py" --workspace "<工作区>" --reviews "<工作区>\98_处理记录\本轮审核.json"
```

批次审核使用以下正式入口：

```powershell
python "<Skill目录>\scripts\review_batches.py" prepare --workspace "<工作区>" --new-run --first-account "李守洲"
python "<Skill目录>\scripts\review_batches.py" current --workspace "<工作区>"
python "<Skill目录>\scripts\review_batches.py" status --workspace "<工作区>"
python "<Skill目录>\scripts\review_batches.py" commit --workspace "<工作区>" --batch 1 --reviews "<工作区>\98_处理记录\批次1审核.json"
python "<Skill目录>\scripts\review_batches.py" sync-account --workspace "<工作区>" --account "已完成的账号名"
python "<Skill目录>\scripts\review_batches.py" confirm-account --workspace "<工作区>" --account "已完成的账号名" --sync-account
python "<Skill目录>\scripts\review_batches.py" finalize --workspace "<工作区>"
python "<Skill目录>\scripts\review_batches.py" prepare-worst-recheck --workspace "<工作区>"
python "<Skill目录>\scripts\review_batches.py" current-worst --workspace "<工作区>"
python "<Skill目录>\scripts\review_batches.py" commit-worst-recheck --workspace "<工作区>" --reviews "<工作区>\98_处理记录\最差复查\批次审核.json"
python "<Skill目录>\scripts\review_batches.py" finalize-worst-recheck --workspace "<工作区>"
python "<Skill目录>\scripts\review_batches.py" prepare-strict-worst-recheck --workspace "<工作区>"
python "<Skill目录>\scripts\review_batches.py" generate-strict-worst-decisions --workspace "<工作区>"
python "<Skill目录>\scripts\review_batches.py" current-strict-worst --workspace "<工作区>"
python "<Skill目录>\scripts\review_batches.py" commit-strict-worst-recheck --workspace "<工作区>" --reviews "<工作区>\98_处理记录\最差严格复核\批次审核.json"
python "<Skill目录>\scripts\review_batches.py" finalize-strict-worst-recheck --workspace "<工作区>"
python "<Skill目录>\scripts\validate_viral_root.py" --workspace "<工作区>"
```

`current` 只返回当前解锁的批次；后续批次虽然保存在内部队列中，但不得交给审核代理。`commit` 会把当前批次写入 `98_处理记录/批次审核/`，并核对标准词根、证据数组、元素和独立审核字段。提交成功后才解锁下一批；账号最后一批完成后进入等待账号确认状态。账号同步会把已完成账号的结果累计写入正式产物，未完成账号不进入正式结果；同步成功后才允许确认并解锁下一个账号。程序拒绝跳过批次。审核批次记录和账号同步结果是正式运行数据，不是测试文件。

`prepare-worst-recheck` 是旧版宽规则的历史入口；当前正式迁移必须使用 `prepare-strict-worst-recheck`。严格复查只从当前正式快照提取关系，不改变原始批次文件；复查全部完成前，正式产物保持不变。完成后将白名单通过项覆盖到累计审核视图、排除其余最差关系并重建正式产物，随后恢复原普通队列的活动批次。

严格最差复核只允许白名单中的直接极端表达：`最坏`、`最差`、`最难吃`、`最难喝`、`最难用`、`最不好`、`最不好的`、`最垃圾`、`最失败`、`最糟`、`最糟糕`、`最黑暗`、`极差`、`极烂`、`一文不值`。`没人看`、`没流量`、`四不像`、`不好用`、`失败`、`死局`等不再属于“最差”。

审核条目示例：

```json
{
  "0e18...": {
    "title": "老实人越来越吃香的时代要来了",
    "analysis": {
      "semantic_summary": "标题讨论老实人在人际或商业环境中的受欢迎程度变化",
      "element_checks": [
        {"element": "人群", "applicable": true, "reason": "老实人是明确的性格人群"},
        {"element": "成本", "applicable": false, "reason": "没有投入、门槛或代价"},
        {"element": "猎奇", "applicable": false, "reason": "没有具体不寻常对象或事件"},
        {"element": "反差", "applicable": false, "reason": "没有完整预期落差关系"},
        {"element": "最差", "applicable": false, "reason": "标题没有直接出现严格白名单中的极端词"},
        {"element": "荷尔蒙", "applicable": false, "reason": "没有两性吸引语境"},
        {"element": "头牌", "applicable": false, "reason": "没有标杆或明确之最"},
        {"element": "怀旧", "applicable": false, "reason": "没有过去生活或旧物场景"}
      ],
      "candidate_summary": "只提出人群词根"
    },
    "decisions": [{
      "root": "老实人",
      "element": "人群",
      "status": "approved",
      "derivation": "直接提取标题中的性格人群名称",
      "rationale": "标题明确指向一类可辨认的性格人群。",
      "evidence": ["老实人"],
      "auditor": "独立复核模型标识",
      "audit_checks": {"root_faithful": true, "evidence_exact": true, "element_valid": true, "reason_supported": true},
      "audit_reason": "词根忠实于标题，证据逐字存在，且该标题确实以此识别人群。"
    }]
  }
}
```

标题键必须使用清理话题后的完整标题。空数组表示该标题已完成语义审核，结论为没有可登记的词根。`status` 可为 `approved`、`rejected` 或 `uncertain`；有争议项须等用户裁定后再同步。JSON 必须是 UTF-8 文件，且位于指定工作区内。

常见退出码：`0` 表示完成或 dry-run 成功；`2` 表示输入、配置、路径或提交错误；`3` 表示仍有未完成或有争议的审核。

## 判断标准

八类元素的定义、边界、爆款词根举例和反例见[八大爆款元素词典](references/八大爆款元素词典.md)；逐题执行模板见[逐题语义审核规范](references/逐题语义审核规范.md)。词根是基于完整标题语义提炼的标准词根，可以由多个标题片段组合，但所有组成信息必须来自标题；`evidence` 必须是逐字出现在清理标题中的非空数组。分类理由和 `derivation` 必须解释标题中的具体表达如何形成词根并符合定义。标题可以有多个词根，也可以没有。

“最差”有唯一硬门槛：标题必须直接出现严格白名单中的极端词，`worst_basis` 固定为 `极端体验`，`worst_trigger` 必须是白名单中的完整词并逐字出现在标题和 `evidence`。`没人看`、`没流量`、`四不像`、`不好用`、`失败`、`死局`、`下策`、`垃圾`等普通负面或失败表达不得靠理由升级为“最差”。旧记录缺少这些字段或触发词不在白名单时，必须排除并重新记录审核结论。

独立复核必须单独检查每一条“标题—词根—元素”关系：原词是否在标题中、归类是否符合定义、理由是否被标题支持。驳回关系保留在审核快照中，不参与热度；未决争议阻止本轮全部正式文件更新。用户对争议项的决定应写入审核记录并保留复核原始意见。

## 热度与结果

单条作品热度按以下公式计算：

```text
点赞 + 评论×1.5 + 收藏×1.2 + 分享×1.5
```

同一作品的完整热度分别计入每个已通过审核的词根。相同词根先把不同选题的完整热度相加，再对汇总结果按四舍五入保留整数；正式汇总表、词典明细标题、词根文件名和同步报告统一使用该整数。词根出现次数按不同作品记录计算；同账号同标题点赞并列最高的多条作品分别计数。

### 词根词典的固定落盘格式

`02_爆款词根/爆款词根词典.md` 必须使用以下层级，不得把词根直接写成二级标题：

```markdown
## 人群

### 具体词根
```

`##` 只允许写八大爆款元素；`###` 才是正式词根。词根的唯一身份是“爆款元素 + 词根”，所以同样的词根文字如果分别被审核为人群和反差，必须在两个元素章节下各自保留，分别计算热度、出现次数和明细链接，不得合并或覆盖。词根明细文件也必须写入对应的 `01_人群` 至 `08_怀旧` 目录；汇总表的“相关选题”链接必须指向该元素目录下的对应文件。只有审核通过的关系才能进入词典、汇总和明细；驳回、待确认和无词根标题只留在批次审核记录中。

正式产物写入：

- `02_爆款词根/爆款词根词典.md`：按“`## 爆款元素` → `### 爆款词根`”组织；每个词根下记录归类理由、标题证据及独立审核结论。同名或近似词根只要元素归属不同，必须保留在各自元素章节，不得跨元素合并。
- `02_爆款词根/爆款词根汇总.md`：编号、词根、元素、汇总热度、出现次数及明细链接。
- `02_爆款词根/01_人群` 至 `08_怀旧`：每个词根的关联作品明细。只使用工作区已配置的八个编号目录，不创建平行分类目录。
- `98_处理记录/source-snapshot.json`：源记录、审核状态、已通过关系、差异及产物映射。
- `98_处理记录/最近一次同步.md`：本次读取、审核、汇总和归档情况。

常规同步仅在标题语义未变化且审核记录符合新版证据数组结构时复用；旧版单字符串证据记录不得直接复用。互动指标变化或源行移动不要求重复判断。标题语义变化则要求新审核。源表读取失败、审核未完成或预检校验失败时，不提交部分结果。批次审核按十条事务推进，已提交批次可恢复；每个账号完成后立即提交该账号的累计正式产物，正式结果不再等待全部账号完成。

## 备份、归档与恢复

每次提交前，将当前受管汇总、词典、明细、快照和同步报告备份到 `98_处理记录/备份/<时间戳>`。不再有效的旧词根明细按快照登记路径归档到 `99_归档`。全量重审时，旧汇总、词典、YAML 旧词典和快照一起归档到带时间戳的重审目录。

提交阶段先在工作区内暂存完整文件集，再逐文件替换。若提交阶段失败，脚本从本轮备份恢复受管文件，并撤回本轮归档移动。归档与备份只处理快照登记或上述明确列出的 Skill 产物；不移动账号源表或其他工作区文件。

## 文件卫生

Skill 源目录只保留正式入口、参考文档和正式运行脚本。测试程序已经并入正式校验逻辑，不再保留 `evals/` 或单元测试脚本；临时调试脚本、`__pycache__`、`.pyc` 和 `.pyo` 不属于发布内容。Excel COM 临时 JSON、提交暂存目录等运行缓存只能放在工作区 `98_处理记录` 下，并在本次运行结束后自动删除；不得在 Skill 目录保存缓存。日常验证使用 `validate_viral_root.py`，它只读检查工作区路径、快照登记产物、分类目录和缓存残留。

---

抖音 / 视频号 / 小红书同名：姜来已来2046
本人微信：jianglai8883
唯一产品：本人24h会员答疑群（找懂的人问就是捷径）

---
