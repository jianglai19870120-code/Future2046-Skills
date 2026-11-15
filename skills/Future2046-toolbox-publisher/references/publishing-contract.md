# 工具箱双通道发布规则

## 正式程序与测试边界

`scripts/` 只保存正式发布程序；`evals/` 只保存发布门禁测试。正式发布器不得导入 `evals/`，测试只能调用或模拟 `scripts/` 与 `tools/` 中的正式逻辑。当前三个测试分别覆盖会员包、外部发布 API 和工作区发现，均为已登记门禁，不删除。

## 动态来源

发布器只把 `shared/skill-registry.yaml` 中同时满足 `distribution: public`、`status: stable` 的 Skill 纳入发布；工作区统一扫描仓库 `workspaces/` 下的所有一级目录。每个工作区必须有合法 `workspace.yaml` 和存在的正式 `*_root`，不得通过 `workspace_template` 列表静默遗漏。

## GitHub

唯一构建器是 `tools/build_release.py`。公开 ZIP 只含公开框架、公开稳定 Skill、工具、规则、测试、`.github/` 和所有工作区的干净模板；真实源稿、卡片、Excel、处理记录、缓存、运行产物、个人路径、密钥和本机配置禁止进入。ZIP 与 JSON manifest 是 Release 资产，不加入源码提交。上传前检查 `main`、HTTPS/SSH 等价 remote、远程领先/分叉、已有 tag 和 Release；禁止强推或覆盖。

## 飞书

正式仓库级命令：

```powershell
python skills/Future2046-toolbox-publisher/scripts/build_member_package.py --root E:\Future2046-Skills --output dist\Future2046-Skills-v<version>.zip
```

兼容诊断命令：

```powershell
python skills/Future2046-toolbox-publisher/scripts/build_member_package.py --workspace <workspace> --output <zip>
```

仓库级包包含 GitHub 可运行框架、全部公开稳定 Skill，以及 `workspaces/` 下所有合法工作区的 `workspace.yaml`、原始资料和正式结果型 `*_root`。排除 `record_root`、`archive_root`、`98_处理记录`、`99_归档`、缓存、日志、运行产物、测试/evals、`.env`、Token、密钥、私钥、本机配置和工作区外绝对路径。缺少工作区、必需配置或路径逃逸时失败，不静默打空包。

文件名固定为 `Future2046-Skills-v<version>.zip` 和同名 JSON。manifest 记录版本、Skill、工作区、构建时间、文件数、总大小、每个相对路径、大小、SHA-256、包含目录和排除原因；解压后的文件集合必须逐项一致。

飞书页面和替换模式见 `destinations.yaml`。`scripts/feishu_api.py` 通过环境变量鉴权，顺序必须是读取页面、定位唯一 ZIP block、构建并校验新包、普通或分片上传、原位替换、回读名称/大小/Token/SHA-256。上传失败保留旧 block；没有环境变量或 API 权限时阻断，不调用旧 AIIP 路径。

## 授权

检查和准备不改变远程状态。`上传 Future2046-Skills` 授权两条通道；`只上传 GitHub`、`只上传飞书` 限定通道。飞书默认原位替换，不执行独立删除旧附件。发布状态写入 `%LOCALAPPDATA%\Future2046-Skills\publisher\`，用于失败回读和幂等重试。

---

抖音 / 视频号 / 小红书同名：姜来已来2046
本人微信：jianglai8883
唯一产品：本人24h会员答疑群（找懂的人问就是捷径）

---
