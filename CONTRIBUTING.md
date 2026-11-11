# 贡献说明

欢迎通过 Issue 报告问题或提出建议。提交代码、规则、文档或测试前，请先说明：

- 修改解决的具体问题；
- 影响的 Skill、工作区或发布契约；
- 是否改变现有输出格式或兼容性；
- 如何验证修改没有泄露工作区资料。

提交内容必须由提交者创作，或提交者拥有充分授权。提交 Pull Request 即表示提交者允许项目在本仓库 `LICENSE` 或后续适用的贡献条款下使用、修改和发布该贡献。

不要提交：

- `workspaces/` 中的真实资料、卡片、日志和 Excel；
- API 密钥、个人路径、临时运行文件和缓存；
- 未获授权转载的第三方文档、提示词或知识库内容。

行为问题或安全问题请通过上述微信私下报告，不要把敏感材料直接贴到公开 Issue。

抖音 / 视频号 / 小红书同名：姜来已来2046

本人微信：jianglai8883

唯一产品：本人24h会员答疑群（找懂的人问就是捷径）

## 新增 Skill

1. 为单一职责确定调用名 `future2046-<名称>`，建立 `skills/Future2046-<名称>/`，写 `SKILL.md`、`skill.yaml`、`agents/openai.yaml` 和包内 README；其他资源按需创建。
2. 在 `SKILL.md` frontmatter 写清 `metadata.future2046_handoff` 的 `accepts`、`produces`、`excludes`，供统一入口筛选；具体业务规则只留在该 Skill 包内。不要把某个 Skill 的业务流程写进根文档或 `shared/`。
3. 需要持续存储资料时增加中文空白工作区模板及 `workspace.yaml`；否则在注册表与包元数据中将 `workspace_template` 设为空字符串。
4. 在 `shared/skill-registry.yaml` 登记版本、状态、安装目标和实际测试入口；运行 `python tools/generate_router_catalog.py --write` 更新入口目录快照。在根 README 与 `docs/新手入门.md` 增加对应目录项和包内链接。该注册表是唯一登记真源，不另建第二份 Skill 清单。
5. 更新 `VERSION`、`CHANGELOG.md` 及各包版本，验证、构建并同步安装。已有 Skill 修改了 frontmatter 或正文时，也必须重新生成目录快照。
6. 创建或修改 Skill 时使用 `$future2046-skill-maker` 的方案、确认、验证和回退规则；发布前运行 Future2046 纯净性检查，不得把未授权外部标识、用户资料或本机配置写入仓库或发布包。

## 校验、安装与下线

先运行 `python -m pip install -r requirements.txt`，再依次运行：

```powershell
python tools/validate_repository.py --root .
python tools/test_multiskill_framework.py --root .
python tools/build_release.py --root .
python tools/test_release_install.py --root .
powershell -ExecutionPolicy Bypass -File tools/sync_codex_install.ps1
```

Codex 安装后用 `tools/verify_codex_install.py` 对比源包与安装包。下线 Skill 先调整注册状态与目录快照，再处理确认归属的安装副本；不得顺带删除个人工作区。`shared/` 只保留注册表；只有多个 Skill 真实共用同一运行契约时，才新增共享真源并配套同步校验。Git 提交和远端发布按单独授权执行。
