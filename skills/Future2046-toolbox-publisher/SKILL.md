---
name: future2046-toolbox-publisher
description: Future2046 双通道发布总控：动态发现公开稳定 Skill，完成版本、结构、Bug、范围和安装门禁，构建 GitHub 公开包与飞书会员全量包，并在明确授权后通过内置 API 发布。
metadata:
  future2046_handoff:
    accepts: "检查、准备或上传 Future2046-Skills；支持全部通道、仅 GitHub 或仅飞书。"
    produces: "双通道门禁报告、ZIP、逐文件 SHA-256 manifest、远程回读结果。"
    excludes: "不把真实会员资料放入 GitHub；不把处理记录、缓存、运行产物、测试、归档、密钥或本机配置放入飞书包。"
---

# 工具箱发布

## 调用意图

- `检查 Future2046-Skills`：只检查，不构建、不上传。
- `准备上传 Future2046-Skills`：完整门禁并生成两个包，不上传。
- `上传 Future2046-Skills`：执行 GitHub 与飞书两条通道；删除飞书旧附件前仍须单独确认。
- `只上传 GitHub` / `只上传飞书`：只执行指定通道，不触碰另一通道。

没有明确上传意图时只停在本地准备阶段。任何门禁失败都标记为不可上传。

## 固定流程

```text
读取 VERSION、registry 和 destinations.yaml
→ 动态发现 distribution: public 且 status: stable 的全部 Skill，以及 workspaces/ 下所有一级工作区
→ 检查版本、注册表、路由、结构、行为、程序边界、公开范围、敏感文件、Git/远程状态
→ 复用 tools/build_release.py 构建 GitHub 公开包
→ 用 scripts/build_member_package.py --root 构建飞书全量包
→ 解压逐文件核对 manifest、大小、SHA-256 和相对路径
→ 明确授权后执行对应上传并回读验证
```

发布规则永远读取 `shared/skill-registry.yaml`，不写死当前 Skill 数量；工作区则统一扫描仓库 `workspaces/` 下的所有一级目录。以后新增 Skill 或工作区，只要满足对应结构和全部门禁，就会自动进入下一次适用发布。

## 两个通道的边界

GitHub 继续唯一使用 `tools/build_release.py --root <repo>`。它发布公开源码框架、公开稳定 Skill、工具、规则、测试、`.github/` 和 `workspaces/` 下所有工作区的干净模板；真实源稿、正式卡片、Excel、记录、缓存、运行产物、个人路径和本机配置不得进入公开资产。提交、推送、Tag、Release 和资产回读由 `scripts/github_release.py` 通过 SSH 与 Git Credential Manager 完成，不依赖旧系统或 `gh` CLI。

飞书使用：

```powershell
python skills/Future2046-toolbox-publisher/scripts/build_member_package.py `
  --root E:\Future2046-Skills `
  --output dist\Future2046-Skills-v<version>.zip
```

它聚合公开稳定 Skill 与 `workspaces/` 下所有合法工作区的 `workspace.yaml`、原始资料和正式结果型 `*_root`；排除 `record_root`、`archive_root`、`98_处理记录`、`99_归档`、缓存、日志、运行产物、测试/evals、`.env`、Token、密钥和外部绝对路径。任何一级工作区缺少 `workspace.yaml` 或正式目录时阻断发布。旧版单工作区诊断仍可用 `--workspace`。

飞书上传由 `scripts/feishu_api.py` 自包含完成：通过 `AI_VIRAL_FEISHU_APP_ID`、`AI_VIRAL_FEISHU_APP_SECRET` 和 `AI_VIRAL_FEISHU_ROOT_URL` 鉴权，读取固定 Wiki 页面，上传新 ZIP，原位替换唯一 ZIP block，并回读名称、大小、Token 和 SHA-256。运行时不得导入或调用 `E:\AIIP获客工厂`。

## 门禁与授权

## 程序边界

- `scripts/` 是正式发布程序：构建、预检、GitHub 发布、飞书上传和总控只能调用这里的正式逻辑。
- `evals/` 是发布门禁测试：只能调用或模拟正式程序，不能被正式发布路径导入。
- 已登记测试用于验证会员包范围、飞书/ GitHub API 边界和工作区发现；它们不是可替代的上传程序，也不应因名称含有 `test` 而删除。

至少执行版本一致性、注册表、路由、程序边界、Skill 结构/行为、仓库链接、公开范围、Git 状态/远程状态、两个包构建、干净安装、manifest/ZIP 逐文件校验和敏感路径扫描。统一总控为 `scripts/publisher.py --mode check|prepare|publish|github|feishu`。工作区已有修改只报告，不擅自提交、覆盖、强推或删除。

GitHub 上传包含提交、推送、`v<version>` tag、Release 资产和回读；已有 tag、Release、远程领先/分叉、分支不符或权限失败即停止。状态文件写入 `%LOCALAPPDATA%\Future2046-Skills\publisher\`。仓库不保存飞书登录信息或 Token；缺少飞书环境变量或 API 权限时停止并报告，不伪造成功。

---

抖音 / 视频号 / 小红书同名：姜来已来2046
本人微信：jianglai8883
唯一产品：本人24h会员答疑群（找懂的人问就是捷径）

---
