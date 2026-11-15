# 工具箱双通道发布规则

## 动态来源

发布器只把 `shared/skill-registry.yaml` 中同时满足 `distribution: public`、`status: stable` 的 Skill 纳入发布，并读取其 `package_path` 和 `workspace_template`。新增 Skill 或登记工作区无需修改发布器；未登记、未生成路由或版本不一致时阻断。

## GitHub

唯一构建器是 `tools/build_release.py`。公开 ZIP 只含公开框架、公开稳定 Skill、工具、规则、测试和干净模板；真实源稿、卡片、处理记录、缓存、运行产物、个人路径、密钥和本机配置禁止进入。ZIP 与 JSON manifest 是 Release 资产，不加入源码提交。上传前检查 `main`、固定 remote、远程领先/分叉、已有 tag 和 Release 资产；禁止强推或覆盖。

## 飞书

正式仓库级命令：

```powershell
python skills/Future2046-toolbox-publisher/scripts/build_member_package.py --root E:\Future2046-Skills --output dist\Future2046-Skills-v<version>.zip
```

兼容诊断命令：

```powershell
python skills/Future2046-toolbox-publisher/scripts/build_member_package.py --workspace <workspace> --output <zip>
```

仓库级包包含 GitHub 可运行框架、全部公开稳定 Skill，以及所有登记工作区的 `workspace.yaml`、原始资料和正式结果型 `*_root`。排除 `record_root`、`archive_root`、`98_处理记录`、`99_归档`、缓存、日志、运行产物、测试/evals、`.env`、Token、密钥、私钥、本机配置和工作区外绝对路径。缺少登记工作区、必需配置或路径逃逸时失败，不静默打空包。

文件名固定为 `Future2046-Skills-v<version>.zip` 和同名 JSON。manifest 记录版本、Skill、工作区、构建时间、文件数、总大小、每个相对路径、大小、SHA-256、包含目录和排除原因；解压后的文件集合必须逐项一致。

飞书页面和替换模式见 `destinations.yaml`。顺序必须是读取页面、构建并校验新包、上传新包、回读名称/大小、单独确认后删除旧包、再次回读。上传失败保留旧包；没有连接器时报告“包已准备、飞书待上传”。

## 授权

检查和准备不改变远程状态。`上传 Future2046-Skills` 授权两条通道；`只上传 GitHub`、`只上传飞书` 限定通道。飞书旧附件删除永远需要删除前的再次确认。

---

抖音 / 视频号 / 小红书同名：姜来已来2046
本人微信：jianglai8883
唯一产品：本人24h会员答疑群（找懂的人问就是捷径）

---
