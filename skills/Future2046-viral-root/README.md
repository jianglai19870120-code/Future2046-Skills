# 爆款词根 Skill

本 Skill 从对标账号作品表中提取标题与互动数，按八大爆款元素审核词根，计算热度，并维护词根词典、汇总表和逐词根选题明细。

热度按“点赞 + 评论×1.5 + 收藏×1.2 + 分享×1.5”计算；同一词根的不同选题先合计完整热度，再四舍五入保留整数。

“最差”只用于标题中直接出现严格白名单里的极端表达：最坏、最差、最难吃、最难喝、最难用、最不好、最不好的、最垃圾、最失败、最糟、最糟糕、最黑暗、极差、极烂、一文不值。没人看、没流量、四不像、失败、死局等不再自动归入最差；具体硬门槛见[逐题语义审核规范](references/逐题语义审核规范.md)。

## 快速使用

在 Codex 中输入：

```text
$future2046-viral-root 同步爆款词根工作区
```

首次处理或标题发生变化时，Skill 按“一个账号→当前每批 10 条→逐题语义概括→八类逐项排查→词根提炼→独立复核→批次落盘→下一批”的顺序执行。历史规则升级后，先完成“最差”关系复查，再恢复普通队列；复查期间正式产物不变。账号最后一批提交后，立即同步截至当前已完成账号的正式词典、汇总表、词根明细、快照和同步报告；同步成功后才确认账号并解锁下一个账号。未完成账号不进入正式结果。标准词根可以是标题多个证据片段提炼出的语义组合，但不能添加原标题没有表达的信息。无词根标题也必须留下八类排查和排除理由。审核批次保存在工作区 `98_处理记录/批次审核`，可断点续跑。未处理的标题不能默认视为“无词根”。

## 工作区产物

| 文件或目录 | 内容 |
|---|---|
| `02_爆款词根/爆款词根词典.md` | 按 `## 爆款元素`、`### 爆款词根` 分层保存已通过审核的词根、分类理由和标题证据 |
| `02_爆款词根/爆款词根汇总.md` | 词根热度、出现次数和指向明细的链接 |
| `02_爆款词根/01_人群`–`08_怀旧` | 按八类元素存放的作品明细 |
| `98_处理记录` | 审核输入、同步快照、差异、备份和运行记录 |
| `99_归档` | 已失效或全量重审前的受管产物 |

## 正式运行入口

```powershell
python "<Skill目录>\scripts\review_batches.py" prepare --workspace "<工作区>" --new-run --first-account "李守洲"
python "<Skill目录>\scripts\review_batches.py" current --workspace "<工作区>"
python "<Skill目录>\scripts\review_batches.py" commit --workspace "<工作区>" --batch 1 --reviews "<工作区>\98_处理记录\批次1审核.json"
python "<Skill目录>\scripts\review_batches.py" sync-account --workspace "<工作区>" --account "已完成的账号名"
python "<Skill目录>\scripts\review_batches.py" confirm-account --workspace "<工作区>" --account "已完成的账号名" --sync-account
python "<Skill目录>\scripts\review_batches.py" finalize --workspace "<工作区>"
python "<Skill目录>\scripts\validate_viral_root.py" --workspace "<工作区>"
python "<Skill目录>\scripts\sync_viral_roots.py" --workspace "<工作区>" --reviews "<工作区>\98_处理记录\本轮审核_已完成.json" --dry-run
```

Skill 发布目录不保存测试程序、调试文件或 Python 缓存。生产校验由 `validate_viral_root.py` 完成；运行时临时文件只允许出现在工作区 `98_处理记录`，运行结束后自动清理。

八大元素的定义、边界、爆款词根举例和反例见[八大爆款元素词典](references/八大爆款元素词典.md)；逐题审核模板见[逐题语义审核规范](references/逐题语义审核规范.md)。完整执行规则、命令、审核 JSON 格式和恢复说明见[SKILL.md](SKILL.md)。

## 数据边界

账号 Excel 保存在本机工作区，只读处理。旧版 `.xls` 通过本机 Excel COM 读取；中文读取失败时停止，不用乱码结果继续生成。真实账号数据、审核记录和快照不属于 Skill 发布包。

---

抖音 / 视频号 / 小红书同名：姜来已来2046
本人微信：jianglai8883
唯一产品：本人24h会员答疑群（找懂的人问就是捷径）

---
