# Ubuntu x86_64 温控与目录包支持：设计说明

日期：2026-10-24
状态：方案已确认，待用户审阅书面规格

## 目标与边界

在现有 macOS、Windows 实现上增加 Linux x86_64 支持。首版验收目标是用户的 Ubuntu 26.04.1 LTS 实体机（Intel Core i7-8700K）。沿用现有局域网净化器控制、最爱档温控策略、手动启动和私有 token 文件，不增加登录自启、云端通信、32 位 x86、其他 Linux 发行版的兼容承诺或跨系统编译。旧的可迁移目录包设计文档中的“不支持 Linux”边界由本扩展规格取代；其他安全约束继续有效。

目标机只读检查已确认 `x86_64` 架构，并暴露 `coretemp` 的 `Package id 0` CPU 温度。当前宿主 Python 为 3.14.4，且没有 `pip`；Docker 可用。因此首版构建路径使用 Linux x86_64 原生 Python 3.11 环境，可在该 Ubuntu 主机上通过隔离容器提供，不修改系统 Python。构建产物仍需在这台 Ubuntu 宿主上运行验证。PyInstaller 不做跨系统编译，Linux 的 `glibc` 兼容性也不保证从较新系统构建的包可在较旧系统上运行。

## 方案选择

推荐直接读取 Linux `hwmon` 中 `coretemp` 的 `Package id N` 传感器：它是目标机已暴露的 CPU Package 温度，无须目标机安装额外探针。备选方案是调用 `lm-sensors` 命令，但会增加目标机依赖并要求解析面向人的输出；本版不采用。若有多个 CPU Package，使用其中最高的有效温度作为控制输入；不把主板、Wi-Fi、ACPI 或其他热区温度冒充 CPU 温度。

读取器每次采样都按 `name=coretemp` 和 `temp*_label=Package id N` 发现对应的 `temp*_input`，不固化 `hwmon2` 等会随重启变化的编号。将毫摄氏度转换为摄氏度后沿用现有有效温度范围校验；若任一匹配的 CPU Package 读数无效，整次采样失败，避免忽略可能更热的 CPU。找不到传感器、读取失败或权限不足时也产生传感器错误，不静默回退到不明热区。

## 程序与配置

`platform` 新增 `linux`，仍必须与当前系统匹配。`temperature_sensor` 继续只接受 `cpu`；Linux 使用新的 `LinuxTemperatureSource`，macOS/Windows 的探针保持不变。净化器控制适配器、阈值、持续时间、最爱档级别及局域网 token 文件格式不变。`config.example.toml` 和 README 增加 Linux 配置、构建及运行说明。

`check` 保持只读：先读可信 CPU 温度，再查询净化器型号和状态。启动 `run` 时，首次成功读到 CPU 温度之前不得向净化器发送开机或档位写命令；这项安全门槛适用于所有平台，并需为原有行为变化补回归测试。运行后若温度探针暂时故障，沿用现有策略：不把故障样本视作低温或高温，不触发新档位切换，继续尝试恢复。停止程序仍不自动恢复净化器的电源和档位。

## Linux 目录包

在 Linux x86_64 构建机上，沿用 PyInstaller 单目录模式生成 `dist/linux-x86_64/`。包内包含 `app/`、公开的 `config.example.toml`、`README.txt`、可执行的 `check.sh` 和 `run.sh`；Linux CPU 温度从目标机 `/sys/class/hwmon/` 读取，不随包附带探针，也不要求目标机安装 Python。启动脚本从包目录定位 `config.toml`，不依赖调用者的当前目录。构建器明确拒绝 Linux 非 x86_64 架构及从 macOS/Windows 交叉构建 Linux 包。

构建沿用已有临时目录和成功后发布机制，不覆盖既有输出目录。不读取或复制 `config.toml`、`.secrets/`、token；模板仅包含已批准的公开默认值。目标机由用户复制模板、设置 IP、单独保存 token，并先执行只读 `check.sh`。若包内程序或脚本缺失、架构不符或构建步骤失败，不发布貌似可用的成品包；目标机传感器不可用则由 `check.sh` 报错，而不是假定构建机可以预知目标机硬件。

## 验证与验收

1. 使用假 `hwmon` 目录和假设备补测试：传感器发现、多个 Package 取最高值、毫摄氏度转换、无效/缺失/权限错误、Linux 平台校验，以及首次有效温度前不得写入净化器。自动化测试不得连接真实净化器。
2. 补 Linux 打包测试：原生平台与架构检查、目录结构、启动脚本、模板平台、私有文件排除、失败时不发布、已有输出不覆盖；运行完整 Python 单元测试和 `git diff --check`。
3. 在用户的 Ubuntu 26.04 x86_64 上构建目录包，检查包内可执行程序的帮助入口及温度读取。若有该机器自己的 token 与局域网连通条件，再运行只读 `check.sh`；没有这些条件时明确报告未完成设备连接验证。
4. 真实 `run.sh` 会改变净化器状态，只在用户明确要求且在场时验收：先只读记录原状态，短时运行，停止后恢复原状态并读回确认。未完成真实写控制前，不宣称 Linux 真机控制已验收。

## 兼容性依据

PyInstaller 官方文档说明必须在目标操作系统上构建，Linux 产物不打包 `glibc`，通常需要在计划支持的最旧 Linux 版本上构建；当前 PyInstaller 6.x 已支持 Python 3.14，但本项目保持 Python 3.11 作为已验证的构建基线。参考：<https://pyinstaller.org/en/stable/usage.html>、<https://github.com/pyinstaller/pyinstaller/blob/v6.22.3/README.rst>。
