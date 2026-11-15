# Future2046 系统工具

`tools/` 只保存整个 Future2046-Skills 仓库共用的维护程序，不保存任何单个 Skill 的业务处理程序。

## 目录边界

- 某个程序需要理解特定 Skill 的卡片、源稿、工作区或业务阶段时，必须放入该 Skill 的 `scripts/`。
- 某个程序服务于注册表、路由、版本、公开范围、发布包、安装副本或整个框架时，必须放入 `tools/`。
- `tools/` 中的 `test_*.py` 是整个 Future2046 框架的系统测试；单个 Skill 的测试只能放在该包的 `evals/`，并在注册表登记。
- `tools/` 不得保存用户资料、工作区运行记录、缓存或任何单一 Skill 的业务逻辑。
- 根工具与没有工作区缓存契约的 Skill 程序默认不保留 Python 字节码缓存；`__pycache__`、`.pyc` 和 `.pyo` 出现在源包即视为目录边界错误。

## 注册表与路由

| 程序 | 用途 |
|---|---|
| `read_registry.py` | 将注册表提供给安装与维护工具读取。 |
| `check_skill_registry.py` | 校验所有 Skill、元数据和工作区模板登记。 |
| `check_version_consistency.py` | 校验根版本、注册表和包版本一致。 |
| `generate_router_catalog.py` | 生成或校验统一入口的 Skill 路由目录。 |

## 仓库边界与质量

| 程序 | 用途 |
|---|---|
| `brand_footer.py` | 校验正式人类可读 Markdown 的品牌尾注。 |
| `check_future2046_purity.py` | 检查不应出现的外部标识残留。 |
| `check_public_scope.py` | 阻止私有资料、缓存和机器路径进入公开包。 |
| `check_program_boundaries.py` | 校验系统工具、Skill 运行程序与 Skill 测试的目录归属。 |
| `validate_repository.py` | 执行仓库级结构、边界与行为校验。 |

## 发布与安装

| 程序 | 用途 |
|---|---|
| `build_release.py` | 构建公开发布 ZIP 与 manifest。 |
| `sync_codex_install.ps1` | 同步登记的公开 Skill 到 Codex 安装目录。 |
| `verify_codex_install.py` | 逐文件核对源 Skill 与安装副本。 |

## 系统测试

| 程序 | 用途 |
|---|---|
| `test_multiskill_framework.py` | 在隔离样本中测试多 Skill 注册、路由、构建与安装。 |
| `test_release_install.py` | 测试发布包解压、模板复制和干净安装。 |

运行完整校验：

```powershell
python tools/check_program_boundaries.py --root .
python tools/validate_repository.py --root .
```

---

抖音 / 视频号 / 小红书同名：姜来已来2046
本人微信：jianglai8883
唯一产品：本人24h会员答疑群（找懂的人问就是捷径）

---
