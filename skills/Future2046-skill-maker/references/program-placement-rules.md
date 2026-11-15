# 程序放置规则

## 两层程序边界

`skills/<Skill>/scripts/` 保存该 Skill 的正式业务运行程序。它们可以读取该 Skill 的输入、工作区配置和阶段状态，并按照该 Skill 的业务契约写入正式产物。

`tools/` 保存整个 Future2046-Skills 的系统程序。它们只处理注册表、路由、版本、安装、发布、公开边界或全框架校验，不应理解任何单一 Skill 的卡片字段、业务阶段或用户工作区数据。

## 测试与辅助模块

- 单个 Skill 的测试只能放入该包 `evals/`，使用 `test_` 前缀，并在 `shared/skill-registry.yaml` 的 `tests` 登记。
- 全框架测试保留在 `tools/`，使用 `test_` 前缀。
- 可被同一 Skill 的多个运行脚本导入、但不需要单独运行的辅助模块，也放在该 Skill 的 `scripts/`。
- 可执行程序不得放入 `references/`、`agents/`、工作区、仓库根目录或 `shared/`。

## 新增程序前的判断

先问：它是否需要理解某一个 Skill 的业务对象？如果需要，放入该 Skill 的 `scripts/`；如果不需要且服务全部登记 Skill，放入 `tools/`。不确定时先在方案中写明归属，再创建文件。

使用 `python tools/check_program_boundaries.py --root .` 验证目录归属；该检查失败时不得构建发布包或同步安装副本。

---

抖音 / 视频号 / 小红书同名：姜来已来2046
本人微信：jianglai8883
唯一产品：本人24h会员答疑群（找懂的人问就是捷径）

---
