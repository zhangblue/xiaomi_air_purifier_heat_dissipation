# README Linux x86_64 安装与运行实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在 README 补齐 Ubuntu 26.04 x86_64 的源码安装、只读检查和手动运行说明。

**架构：** Linux 章节与现有 macOS、Windows 源码安装章节并列，预构建目录包继续链接 `docs/bundle-build.md`。文档静态测试保护关键命令、传感器前提和密钥边界，不运行真实设备。

**技术栈：** Markdown、Python 3.11、`unittest`、Linux `coretemp` sysfs。

**任务 1 执行记录：** 步骤 1–4 已完成：新增命令契约回归测试，先观察 Linux 章节缺失导致的 RED，再补齐 README；聚焦 2 项、完整 110 项测试通过，`git diff --check` 通过。步骤 5 的任务文件提交由实现代理完成；独立审查、本地 main 集成与推送由主代理继续执行，不在实现代理范围内。未连接真实设备，也未读取私有配置或 token。

---

## 文件职责

- `README.md`：新增 Linux x86_64 安装与运行章节；保留 macOS/Windows 与打包指南入口。
- `tests/test_bundle.py`：为该章节增加文档回归测试。

### 任务 1：Linux 源码安装与手动运行章节

**文件：** `README.md`、`tests/test_bundle.py`

- [ ] **步骤 1：写失败测试。** 在 `LinuxDocumentationTests` 新增 `test_readme_explains_linux_source_install_and_manual_run`：读取 README，从 `## Linux x86_64 安装与运行` 截取到 `## 配置与注意事项`，断言包含 `Ubuntu 26.04 x86_64`、`python3.11 -m venv .venv`、`python -m pip install -e .`、`cp config.example.toml config.toml`、`platform = "linux"`、`.secrets/purifier-token`、`coretemp`、`Package id N`、`purifier-control --config config.toml check`、`purifier-control --config config.toml run` 和 `Ctrl+C`；另断言 README 保留 `[跨平台打包指南](docs/bundle-build.md)`。
- [ ] **步骤 2：验证红灯。** 运行 `/Users/zhangdi/works/workspace/github/xiaomi_air_purifier_heat_dissipation/.venv/bin/python -m unittest tests.test_bundle.LinuxDocumentationTests -v`，预期因 Linux 章节缺失而失败；不连接净化器。
- [ ] **步骤 3：最小文档实现。** 在 Windows 章节后添加 Linux 标题：说明 Python 3.11 与 venv、CPU Package `coretemp` 传感器前提；给出 `python3.11 -m venv .venv`、`. .venv/bin/activate`、`python -m pip install -e .`、复制配置的命令。说明确认 `platform = "linux"` 与 `[purifier].host`，用 `getpass` 写入仅包含 token 的 `.secrets/purifier-token`，设置目录 700、文件 600；先运行只读 `check` 并确认可信温度、型号 `zhimi.airpurifier.v6` 和连接，再在场手动 `run`。说明 `Ctrl+C` 不恢复净化器状态，预构建包参阅原有跨平台指南；不新增自启或真实写控制。
- [ ] **步骤 4：验证绿灯。** 运行同一聚焦测试和 `/Users/zhangdi/works/workspace/github/xiaomi_air_purifier_heat_dissipation/.venv/bin/python -m unittest discover -s tests -v`，预期所有测试通过；运行 `git diff --check`。
- [ ] **步骤 5：提交与集成。** 仅提交 README、测试和本计划，提交信息 `docs: add Linux x86_64 runtime setup to README`；独立审查后按用户授权快进合并至本地 `main`，在合并结果上复测，再推送 `origin/main`。不得修改或推送既有 `v0.1.0` tag，也不得暂存主工作区未跟踪的 `config.toml`。
