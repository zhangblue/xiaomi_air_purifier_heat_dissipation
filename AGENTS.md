# 项目协作约定

本项目用 Python 3.11 在 macOS 或 Windows 上读取 CPU 温度，并通过局域网控制小米空气净化器 AC-M3-CA（内部型号 `zhimi.airpurifier.v6`）。先阅读 [README.md](README.md)；设计与实现计划位于 `docs/superpowers/`。

## 开发与验证

- Python 包使用 `src/purifier_control/` 布局，命令入口是 `purifier-control --config config.toml check|run`。
- 修改行为前先补回归测试；运行 `python -m unittest discover -s tests -v`，并在提交前检查 `git diff --check`。
- macOS 温度采集依赖 `smctemp`；Windows 温度探针位于 `windows/TemperatureProbe/`，应在 Windows 上运行 `dotnet test windows/TemperatureProbe.Tests/TemperatureProbe.Tests.csproj`。不要把 macOS 上的 Python 测试通过写成 Windows 真机验收通过。
- 第一版由用户手动启动，不要擅自加入登录自启。温控只使用净化器最爱档，默认高于 60°C 持续 15 秒升至级别 17，低于 55°C 持续 120 秒降至级别 3；这些值在配置中可调整。

## 第三方文档

用户询问库、框架、SDK、API、CLI 或云服务时，优先通过 Context7 查询当前文档：先按名称和问题调用 `resolve-library-id`，选择最匹配的 `/org/project`，再针对单一概念调用 `query-docs`。若未收录目标库，再核对官方文档或本项目固定版本的源码；不要凭记忆确定接口。

## 密钥与真机操作

- `.secrets/purifier-token` 是私有文件，已由 Git 忽略。不得把 token 写入代码、配置示例、测试夹具、日志、命令行参数或提交；错误信息也不得包含 token。
- `check` 必须只读。自动化测试使用假设备和假传感器，不连接真实净化器。
- 仅在用户明确要求且在场时进行真实写控制验收。先只读记录设备电源、模式和最爱档级别；短时测试后停止程序、恢复原状态，并再次读回确认。若恢复失败，立即告知用户，不要声称验收通过。
