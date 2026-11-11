# 源稿队列规则

## 目的

源稿队列负责为不同命名来源建立稳定的 `queuePosition`，避免依赖“经纬 (N)”这类单一文件名格式，也避免批量继续时回到第一篇。

## 生成方式

运行：

```powershell
python scripts/source_queue.py scan --workspace <工作区> --write
```

脚本读取 `workspace.yaml`、`processing-log.jsonl` 和已有的 `source-queue.json`：

- 已有日志或队列中的位置优先保留；
- 新源稿按相对路径排序，并追加到当前最大位置之后；
- Excel 文件本身不进入少走弯路队列，物化后的 Markdown 才进入队列；
- 当前记录为 `completed`、`skipped` 或 `failed` 时视为终态；
- `new`、`in_progress`、`paused` 没有终态，不能被跳过；
- 活动 run 的源路径必须等于队列选出的当前源稿。

## 选择下一篇

```powershell
python scripts/source_queue.py next --workspace <工作区>
```

输出最小 `queuePosition` 的未取得终态源稿。这个命令只读取和计算；只有加上 `--write` 才会更新 `workspace.yaml` 指定的 `<record_root>/source-queue.json`。

队列文件是可重建缓存，不是源稿处理事实。最终完成状态仍以 V4 `processing-log.jsonl` 和正式提交校验为准。

---

抖音 / 视频号 / 小红书同名：姜来已来2046
本人微信：jianglai8883
唯一产品：本人24h会员答疑群（找懂的人问就是捷径）

---
