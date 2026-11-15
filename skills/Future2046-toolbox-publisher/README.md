# 工具箱发布

`$future2046-toolbox-publisher` 负责 Future2046 的版本同步、发布前检查、GitHub 公开包和飞书会员全量包准备，以及获得授权后的双通道发布。

## 使用方式

```text
$future2046-toolbox-publisher 检查当前版本和上传前问题
```

```text
$future2046-toolbox-publisher 准备 GitHub 和飞书发布包，但先不要上传
```

```text
$future2046-toolbox-publisher 上传 Future2046-Skills
```

默认先检查和准备，不自动上传。

## 两种发布包

- GitHub：复用根目录 `tools/build_release.py`，发布公开大框架、可运行 Skill 和 `workspaces/` 下所有工作区的干净模板，并由内置 API 完成 Release 资产上传。
- 飞书：动态聚合 `workspaces/` 下所有合法工作区的原始资料、正式结果和目录结构，排除处理记录、缓存、运行产物、测试文件和归档。

飞书资料包构建命令：

```powershell
python scripts/build_member_package.py --root E:\Future2046-Skills --output dist\Future2046-Skills-v<version>.zip
```

`--workspace` 仍保留，用于单工作区测试和诊断。飞书由内置 `scripts/feishu_api.py` 通过 Windows 用户环境变量鉴权，采用原位替换唯一 ZIP block；运行时不依赖 `E:\AIIP获客工厂`。

完整规则见 [发布规则](references/publishing-contract.md)。总控接口为 `scripts/publisher.py --mode check|prepare|publish|github|feishu`。

`scripts/` 保存正式发布程序；`evals/` 保存已登记的门禁测试。测试不会参与实际上传，也不会被正式脚本导入。

---

抖音 / 视频号 / 小红书同名：姜来已来2046
本人微信：jianglai8883
唯一产品：本人24h会员答疑群（找懂的人问就是捷径）

---
