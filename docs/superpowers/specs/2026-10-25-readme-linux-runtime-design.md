# README Linux x86_64 安装与运行章节设计

## 目标

在 README 的 macOS、Windows 源码安装章节后补齐 Linux x86_64 对等章节，让使用 Ubuntu 26.04 x86_64 的读者能手动安装、先只读检查、再运行温控程序。现有跨平台目录包指南继续负责预构建包的构建和迁移细节，README 只提供入口链接，不复制整套目录包说明。

## 章节内容

新增标题 `## Linux x86_64 安装与运行`，放在 Windows 章节与“配置与注意事项”之间。说明系统需要可用的 Python 3.11 和 venv 支持；使用项目目录内 `.venv` 安装 `purifier-control`，不替换 Ubuntu 系统 Python。示例命令依次创建虚拟环境、安装项目、复制 `config.example.toml` 到私有 `config.toml`；确认 `platform = "linux"`，按需修改净化器 host。

私有 token 仅写入 `.secrets/purifier-token`，示例使用不回显输入并设置目录及文件权限。不得把 token 写入命令参数、配置模板或 README 示例值。明确 Linux 温度采集只支持 `/sys/class/hwmon` 中 `coretemp` 的 CPU Package 标签 `Package id N`；缺少该传感器或读数无效时不应运行控制。

命令示例先执行 `purifier-control --config config.toml check`，要求确认可信温度、`zhimi.airpurifier.v6` 型号和局域网连接，再在用户在场时手动执行 `purifier-control --config config.toml run`。写明 `Ctrl+C` 停止后不会自动关闭净化器或恢复原档位。预构建包使用者通过现有 `[跨平台打包指南](docs/bundle-build.md)` 获取目标机步骤；不在本章节重新叙述 `check.sh`、`run.sh` 全套打包流程。

## 验证边界

补充文档静态回归测试，核对 README 的 Linux 章节、关键安装/检查/运行命令、传感器限制、token 私有文件及目录包指南链接。先验证测试在文档修改前失败，再修改 README 使其通过。运行完整 Python 测试与 `git diff --check`。文档修改不触碰真实净化器、不新增自动启动，也不宣称 Ubuntu 真机验收通过。
