# Future2046 Skills

一组可独立安装、也可以通过统一入口调用的中文 Agent Skills。

**当前版本：** `1.3.2`　|　[许可证](LICENSE)

## Future2046 是什么

Future2046 Skills 是由博主姜来已来2046开发的，个人IP×商业创业×能力成长×财富增值×生活方式于一体的技能工具箱。
它是一个可持续扩展的 Skill 集合。每个 Skill 只负责一类明确能力，并把自己的执行规则、输入边界、输出格式和验证方式保存在自己的 Skill 包内。

`$future2046` 是统一调用入口。当你不知道该使用哪个 Skill，或者一个任务确实需要多个能力衔接时，可以把目标直接交给它。已经知道要使用哪个能力时，也可以直接调用具体 Skill。

当前可以使用：

- 通过统一入口选择已安装且有效的 Skill；
- 围绕具体行业，读取文章、书籍、访谈、视频文稿或 Excel 行文稿，持续提炼行业常见的坑、错误认知和需要避开的做法，帮助你提前避坑、少走弯路，并形成可调用的误区卡；
- 将来继续增加新的、单一职责的 Skill；
- 单独安装某个 Skill，或安装整个 Future2046 集合。

具体 Skill 的业务流程不写在项目总 README 中，而是由对应 Skill 包内的 `SKILL.md` 和参考文件负责。

## 快速开始

### 第 1 步：安装

在 PowerShell 中进入仓库目录，运行：

```powershell
& .\tools\sync_codex_install.ps1
```

默认会把已登记且支持 Codex 的正式 Skill 安装到：

```text
%USERPROFILE%\.codex\skills
```

也可以只安装一个 Skill：

```powershell
& .\tools\sync_codex_install.ps1 -SkillId future2046-avoid-pitfalls
```

指定单个成员 Skill 时，安装脚本会同时安装统一入口，方便后续继续调度。

### 第 2 步：调用统一入口

在 Codex 对话中输入：

```text
$future2046 新手入门
```

或者直接描述任务：

```text
$future2046 我有一篇视频文稿，想找出其中的错误认知
```

### 第 3 步：在同一个对话中继续

收到结果后，可以直接补充材料、范围或修改意见，不需要每轮重新输入 Skill 名称。

如果换成完全不同的任务，再次输入 `$future2046`；如果你已经明确知道要用哪个能力，也可以直接调用具体 Skill。

## `$future2046` 怎样安排 Skill

统一入口按最终目标选择能力：

```text
1. 识别你想得到的最终结果
2. 扫描已安装且已登记的 Skill
3. 选择最少的匹配能力
4. 读取对应 Skill 的完整规则
5. 在当前对话中执行
6. 根据结果继续、交接或停止
```

入口有以下边界：

- 未安装的 Skill 不会被当作可执行能力；
- 未登记的目录不会进入正式候选；
- 无法读取 Skill 规则时不会强行执行；
- 入口不会替成员 Skill 跳过审核、去重、串行或正式落盘门禁；
- 多个 Skill 只有在确实存在前后依赖时才会组合；
- 入口只负责选择和交接，具体业务结果由成员 Skill 负责。

## 全部 Skill

当前正式 Skill 以 [`shared/skill-registry.yaml`](shared/skill-registry.yaml) 为唯一登记来源。

### 入口

| 命令 | 用途 |
|---|---|
| `$future2046` | 根据任务选择并调用合适的 Future2046 Skill |

### 内容处理

| 命令 | 用途 |
|---|---|
| `$future2046-avoid-pitfalls` | 从行业资料中识别常见坑和错误认知，生成可检索、可复用的误区卡 |

### Skill 工具

| 命令 | 用途 |
|---|---|
| `$future2046-skill-maker` | 创建、改进、测试、同步和发布 Future2046 Skill |

已经知道要使用某个 Skill 时，可以直接调用它。每个 Skill 的详细输入、输出和边界见对应包内的 README 与 `SKILL.md`。

## 安装详情

### 从当前仓库安装

这种方式适合本地开发、更新和维护：

```powershell
Set-Location E:\Future2046-Skills
& .\tools\sync_codex_install.ps1
```

安装脚本会读取注册表，比较源包和 Codex 安装目录的文件差异，只同步已登记、支持 Codex 的 Skill，并验证安装后的文件哈希。

### 使用发布包

生成公开发布包：

```powershell
python -B tools\build_release.py --root E:\Future2046-Skills
```

发布包只包含可公开分享的 Skill 源包、工作区模板、虚构示例、必要文档和安装工具，不包含：

- `workspaces/` 中的个人资料；
- 源文稿、Excel 和误区卡片；
- 处理日志、索引、运行状态和审核证据；
- 缓存、临时文件和本机绝对路径。

### Codex 安装位置

默认安装位置是：

```text
%USERPROFILE%\.codex\skills
```

不要把仓库中的 `workspaces/` 复制到 Skill 安装目录。Skill 包和个人工作区是两类不同资产。

### 安装后看不到 Skill

按以下顺序检查：

1. 安装命令是否成功完成；
2. 目标目录中是否存在对应的 `SKILL.md`；
3. 调用名是否与注册表中的 `id` 一致；
4. 是否已经重新打开 Codex 或新建对话；
5. 是否使用了正确的 `$future2046` 或成员 Skill 调用名。

## 更多用法

### 直接调用具体 Skill

```text
$future2046-avoid-pitfalls
拆解这篇文稿中的误区
```

### 让入口帮助选择

```text
$future2046
我不知道该用哪个 Skill 来处理这批素材
```

### 按顺序批量处理

```text
$future2046-avoid-pitfalls
按源文件顺序处理尚未完成的文稿，一篇完成后再开始下一篇
```

### 指定本地文件

```text
$future2046-avoid-pitfalls
处理：
E:\我的工作区\01_源知识库\视频文稿\示例.md
```

### 建立行业避坑知识库

```text
$future2046-avoid-pitfalls
我正在做连锁餐饮行业，请读取这个文件夹里的文章、访谈和视频文稿，
帮我建立一套行业避坑误区卡。
```

```text
$future2046
我想持续收集教育行业的资料，并把其中反复出现的坑整理成可调用卡片。
```

为了让 Skill 正确执行，尽量同时提供：

- 完整原文或可读取的文件路径；
- 处理范围，例如单篇、全部或前 10 篇；
- 期望结果，例如误区卡、检索已有卡片或只做扫描；
- 需要遵守的分类、命名或输出要求。

## 工作区与数据边界

Future2046 将能力和数据分开管理：

```text
Skill 包       = 可分享的能力
工作区         = 用户自己的数据
源知识库       = 输入
输出目录       = 生成结果
处理记录       = 运行状态
归档目录       = 历史资料
```

通用规则：

- `skills/` 保存可公开的 Skill 源包；
- `workspaces/少走弯路工作区/` 是本机唯一工作区来源；发布时从中提取干净框架，不上传其中的个人资料；
- 真实文稿、Excel、卡片、日志和审核证据不进入 Skill 包；
- Skill 不依赖固定 E 盘或用户名路径；
- 将整个仓库复制到其他位置后，应通过工作区配置重新定位数据目录。

具体工作区字段和业务数据规则由对应 Skill 自己说明，项目总 README 不替代这些规则。

## 更新与帮助

更新 Skill 前先运行仓库检查：

```powershell
python -B tools\validate_repository.py --root E:\Future2046-Skills
python -B tools\test_multiskill_framework.py --root E:\Future2046-Skills
```

构建和验证发布包：

```powershell
python -B tools\build_release.py --root E:\Future2046-Skills
python -B tools\test_release_install.py --root E:\Future2046-Skills
```

更新的固定顺序是：

```text
更新 Skill 源包
→ 更新注册表和入口目录
→ 运行仓库校验
→ 构建发布包
→ 同步 Codex
→ 验证安装目录
```

遇到新增 Skill、版本不一致、入口目录过期或发布范围问题时，参阅[贡献说明](CONTRIBUTING.md)。

## 仓库资料

| 目录或文件 | 用途 |
|---|---|
| [`skills/`](skills/) | Skill 源包 |
| [`workspaces/少走弯路工作区/`](workspaces/少走弯路工作区/) | 本机工作区来源；发布时提取为同路径的干净框架 |
| [`shared/skill-registry.yaml`](shared/skill-registry.yaml) | 所有正式 Skill 的登记真源 |
| [`docs/新手入门.md`](docs/新手入门.md) | 面向第一次使用者的项目入门说明 |
| [`tools/`](tools/) | 校验、目录生成、打包和 Codex 安装工具 |
| `dist/` | 由构建工具生成的发布包 |
| [`DATA-POLICY.md`](DATA-POLICY.md) | 数据公开和私有边界 |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | 新增、修改和维护 Skill 的规则 |

## 贡献与新增 Skill

新增 Skill 时，按[贡献说明](CONTRIBUTING.md)执行：

1. 确定单一职责和调用名；
2. 建立 Skill 包并写好 `SKILL.md`；
3. 在注册表中登记版本、状态、安装目标和测试入口；
4. 生成并校验统一入口目录；
5. 添加包内说明和必要测试；
6. 运行仓库校验、发布构建和安装验证。

新 Skill 的业务流程应留在自己的包内，不要把它扩散到项目根 README、`shared/` 或其他 Skill 中。

## 许可证与联系

使用许可见 [`LICENSE`](LICENSE)，数据边界见 [`DATA-POLICY.md`](DATA-POLICY.md)。

抖音 / 视频号 / 小红书同名：姜来已来2046

本人微信：`jianglai8883`

唯一产品：本人24h会员答疑群（找懂的人问就是捷径）

许可证是项目授权范围的唯一准则。未经授权，不得将本项目或其中的 Skill 重新打包、再分发、出售或用于训练人工智能模型。
