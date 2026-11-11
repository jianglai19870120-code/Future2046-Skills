# 发布与 GitHub 流程

## 上传清单

### GitHub 源仓库应该上传

- 根目录公开文档：`README.md`、`LICENSE`、`NOTICE.md`、`DATA-POLICY.md`、`CONTRIBUTING.md`、`CHANGELOG.md`、`VERSION` 和 `requirements.txt`；
- `docs/`、`shared/`、`tools/` 和不含密钥或个人配置的 `.github/` 工作流；
- 注册表中 `distribution: public` 的 Skill 包，包括 `SKILL.md`、`skill.yaml`、`agents/`、`references/`、`scripts/`、`evals/`、README 和授权说明；
- 工作区中仅用于说明结构的 `README.md`、`workspace.yaml` 和 `*.md.template`。

### GitHub 源仓库不应该上传

- `workspaces/` 中的真实源稿、误区卡、处理记录、索引、运行状态和归档；
- `.xlsx`、`.xls`、`.xlsm` 等业务资料；
- API 密钥、Token、`.env`、个人路径、本机配置和浏览器缓存；
- `__pycache__`、`.pyc`、日志、缓存、临时文件和备份文件；
- 未登记 Skill、未获授权的第三方材料和历史运行记录；
- `dist/` 中的 ZIP、manifest 和临时构建产物；这些只作为 Release 资产上传。

### GitHub Release 应该上传

- `dist/Future2046-Skills-1.3.5.zip`；
- `dist/Future2046-Skills-1.3.5.json`。

Release 资产不进入源码提交。发布前必须用公开范围检查和干净目录安装测试确认内容。

## 发布前

确认仓库所有者、仓库名、可见性、默认分支、发布范围和版本号。检查 Git 状态、远程仓库、未跟踪文件、密钥、个人路径、工作区资料、运行记录和缓存。

## 本地准备

只暂存明确的源文件和发布文件。运行版本、注册表、路由、公开范围、品牌尾注和安装校验。构建发布包后从干净临时目录解压，验证 Skill 文件逐项存在且内容一致。

## 远程动作

创建远程仓库、commit、push、tag 和 Release 都属于外部状态变化。用户未明确授权具体动作时，只交付本地 staging、检查报告和可复制命令；不得自动执行。

## 发布后

使用隔离目录验证公开安装流程，确认安装后的 `SKILL.md`、agents、references、scripts 和 assets 与发布源一致。发现远端分叉、已有 tag、权限失败或包内容异常时停止，不反复覆盖或强推。

---

抖音 / 视频号 / 小红书同名：姜来已来2046
本人微信：jianglai8883
唯一产品：本人24h会员答疑群（找懂的人问就是捷径）

---
