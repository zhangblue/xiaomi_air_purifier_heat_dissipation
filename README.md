# 电脑温度联动米家空气净化器 Pro

在 macOS 或 Windows 上手动运行，读取本机 CPU 温度，并在局域网内控制 AC-M3-CA（设备内部型号 `zhimi.airpurifier.v6`）的最爱档。默认配置在 CPU 温度持续高于 60°C 达 15 秒后使用级别 17；持续低于 55°C 达 120 秒后回到级别 3。级别是设备的最爱档数值，不是转速百分比。首次使用前请确认净化器 IP、型号及这两个级别适用于自己的设备。

净化器增加周围空气流动，**不能代替电脑自身散热或过热保护**。本程序不会控制电脑风扇。第一版只支持手动启动，不安装开机自启服务；`run` 是无需交互的入口，留待以后接入 macOS LaunchAgent 或 Windows 任务计划程序。

## 构建与迁移目录包

目录包可复制到另一台**同操作系统、同 CPU 架构**的电脑，目标机无需另装 Python、Python 包、.NET Runtime 或 `smctemp`。macOS 与 Windows 要分别在对应系统上构建，不能跨系统或跨架构构建；较新系统构建的包也不保证兼容较旧系统。首版 Windows 构建目标为 x64，macOS 为构建机原生架构。目标机仍须能读取 CPU 温度，并能通过局域网访问净化器。目录包不提供自动启动。

在项目根目录准备构建机。macOS 需 Python 3.11、Homebrew 安装的 `narugit/tap/smctemp`；构建器会核对其二进制、来源归档、许可证材料及系统依赖，核对失败就停止构建。Windows 需 Python 3.11 和 .NET 8 SDK。两边均须安装项目的打包依赖：

```sh
# macOS
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[bundle]'
.venv/bin/python -m tools.build_bundle
# 自选尚不存在的输出目录：.venv/bin/python -m tools.build_bundle --output dist/my-mac
```

```powershell
# Windows PowerShell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[bundle]'
.\.venv\Scripts\python.exe -m tools.build_bundle
# 自选尚不存在的输出目录：.\.venv\Scripts\python.exe -m tools.build_bundle --output dist\my-pc
```

默认输出分别为 `dist/macos-<架构>/`、`dist/windows-x64/`。成功时命令会打印包路径；现有输出目录不会被覆盖。将整个目录复制到目标机，在包内复制 `config.example.toml` 为 `config.toml`，修改 `[purifier].host`，并在包内创建 `.secrets/purifier-token`，只写入该设备的 32 位十六进制 token。**token 和私有配置不进入构建包**，也不要把 token 放入命令参数、截图或日志。macOS 可使用下文的无回显输入命令在包目录创建 token；Windows 可使用下文的 PowerShell 命令，并限制文件访问权限。

在目标机先运行只读的 `check.command`（macOS）或 `check.cmd`（Windows），确认温度、型号和设备连接后，在场时手动运行 `run.command` 或 `run.cmd`。按 `Ctrl+C` 停止。程序停止后**不会恢复净化器原来的电源、模式或最爱档级别**，如有需要请自行恢复并确认。macOS 对未签名程序可能显示安全提示，需由电脑所有者在系统设置中批准运行。Windows 有些温度传感器仍需所有者单独安装 PawnIO 驱动；目录包不包含或安装该驱动，不应为此关闭系统安全保护。

macOS 包内 `bin/` 随附 `smctemp` 的 GPL-2.0-only 许可证及固定版本源码归档，供再分发时查阅；随附材料**不等同于法律审核**。本仓库的 macOS Python 测试或离线构建结果也不代表 Windows 已完成打包或目标机验收；需要在相应系统上分别构建并验证。真实设备的 `run` 验收应在用户在场时先记录状态，短时测试、停止、恢复原状态并读回确认。


## macOS 安装与运行

需要 Python 3.11、Homebrew 和同一局域网中的净化器。在仓库目录打开终端：

```sh
brew install python@3.11
brew tap narugit/tap
brew install narugit/tap/smctemp
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install -e .
cp config.example.toml config.toml
```

确认 `config.toml` 顶部是 `platform = "macos"`，按需修改 `[purifier].host`。`smctemp` 必须在运行 `purifier-control` 的终端的 `PATH` 中；可以先执行 `smctemp -c` 确认能读到摄氏温度。

把这台设备的 **32 位十六进制局域网 token** 写入仓库目录下的 `.secrets/purifier-token`，文件内容只放 token，不加引号。不要把 token 写进 `config.toml`、命令行参数、截图或日志。下面的输入提示不会回显 token：

```sh
mkdir -p .secrets
chmod 700 .secrets
python -c 'from getpass import getpass; from pathlib import Path; Path(".secrets/purifier-token").write_text(getpass("Token: "), encoding="ascii")'
chmod 600 .secrets/purifier-token
purifier-control --config config.toml check
purifier-control --config config.toml run
```

`check` 只读取 CPU 温度、设备型号和状态，不更改净化器。预期输出包含 CPU 温度、配置的 IP、`zhimi.airpurifier.v6` 和 `Connection: connected`，不会输出 token。确认检查成功、设备可由你观察和控制后，再执行 `run`。它会开机并立即设置低温最爱档级别；达到高温条件时切换为高级别。按 `Ctrl+C` 停止。**程序停止不会关闭净化器，也不会恢复停止前的档位**；如需关机或调整档位，请在米家 App 或设备上操作。

## Windows 安装与运行

需要 Python 3.11、.NET 8 SDK（构建温度探针）、.NET 8 Runtime（运行探针），以及能读取 CPU 温度传感器的 Windows 电脑。以下命令在仓库目录的 PowerShell 中执行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
dotnet publish .\windows\TemperatureProbe\TemperatureProbe.csproj -c Release -r win-x64 --self-contained false -o .\windows\publish\TemperatureProbe
Copy-Item .\config.example.toml .\config.toml
```

把 `config.toml` 顶部改为 `platform = "windows"`，按需修改 `[purifier].host`。在仓库目录创建 `.secrets\purifier-token`，只保存这台设备的 32 位十六进制局域网 token，不加引号；不要把 token 写进配置、命令行或日志。下面的输入提示不会回显 token。该目录已被 Git 忽略，请在文件属性的“安全”页确认文件仅对你的 Windows 用户账户可读。

让本次 PowerShell 会话能找到发布的探针，然后先检查传感器，再执行程序：

```powershell
New-Item -ItemType Directory -Force .\.secrets | Out-Null
python -c "from getpass import getpass; from pathlib import Path; Path('.secrets/purifier-token').write_text(getpass('Token: '), encoding='ascii')"
$env:PATH = "$(Resolve-Path .\windows\publish\TemperatureProbe);$env:PATH"
TemperatureProbe.exe --json
purifier-control --config .\config.toml check
purifier-control --config .\config.toml run
```

探针应输出含 `temperature_c` 的 JSON。`0°C` 不是有效的 CPU 读数，探针会报错并列出发现的温度传感器。若在 Ryzen 电脑上看到 `Core (Tctl/Tdie)=0`，先确认使用管理员权限；LibreHardwareMonitor 的底层读取还可能需要安装 [PawnIO 官方签名驱动](https://github.com/namazso/PawnIO.Setup/releases)。驱动会取得硬件访问权限，应由电脑所有者决定是否安装；不要为此关闭 Windows 内存完整性等安全保护。安装后重新运行探针，只有读到可信的非零温度且 `check` 成功，再运行 `run`；按 `Ctrl+C` 停止。停止后净化器保持当时的电源和档位状态。

## 配置与注意事项

`config.example.toml` 是可复制的起点。`token_file` 相对 `config.toml` 所在目录解析，默认是 `.secrets/purifier-token`。`platform` 只接受与当前电脑相符的 `macos` 或 `windows`。`temperature_sensor` 当前只支持 `cpu`。默认每 5 秒采样一次；阈值要求低温恢复值小于高温触发值，低级别小于高级别，级别范围为 0–17。

净化器 IP 默认 `192.168.250.118`。如果路由器重新分配地址，请更新 `[purifier].host`。局域网或温度探针暂时不可用时，程序会报告故障并重试；遇到设备拒绝级别时应停止运行并核对可用档位。`check` 报型号不符时请勿运行控制程序。

macOS 的 `check` 已只读实测。2026-09-30 在用户在场时，已对这台净化器短时写入并读回确认最爱档级别 3 和 17；还使用临时配置将高温阈值调至低于当时约 40°C 的 CPU 温度，验证程序从级别 3 自动升至 17。测试结束后，设备读回为原来的开机、Auto 模式、最爱档记录值 0。

2026-10-01 在用户在场时，Windows 电脑的 `check` 成功读取到 56.0°C 的 CPU 温度，确认净化器型号为 `zhimi.airpurifier.v6` 且连接正常。短时运行 `run` 后，程序将净化器切到最爱档级别 3，并通过设备状态独立读回确认。结束运行后，净化器已恢复到测试前的开机、静音模式、最爱档记录值 0，且再次读回确认。本次 Windows 测试未观察到持续高于 60°C，因此默认高温条件下自动切换至级别 17 尚未实机验证；长时间运行与睡眠恢复也仍需继续观察。

### 如何获取 token

可使用 [Xiaomi Cloud Tokens Extractor](https://github.com/PiotrMachowski/Xiaomi-cloud-tokens-extractor) 获取局域网 token。按该项目的说明运行工具，通过米家账号或扫码登录，选择设备所在的服务器区域（不确定时可留空检查所有区域），再按净化器的名称或 IP 地址找到对应设备并复制 token。此工具可能列出账号下其他设备的 token，请勿分享完整输出；将这台净化器的 token 按下文保存到 `.secrets/purifier-token`，不要提交到 Git。
