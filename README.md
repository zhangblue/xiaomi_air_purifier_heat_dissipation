# 电脑温度联动米家空气净化器 Pro

在 macOS 或 Windows 上手动运行，读取本机 CPU 温度，并在局域网内控制 AC-M3-CA（设备内部型号 `zhimi.airpurifier.v6`）的最爱档。默认配置在 CPU 温度持续高于 60°C 达 15 秒后使用级别 17；持续低于 55°C 达 120 秒后回到级别 3。级别是设备的最爱档数值，不是转速百分比。首次使用前请确认净化器 IP、型号及这两个级别适用于自己的设备。

净化器增加周围空气流动，**不能代替电脑自身散热或过热保护**。本程序不会控制电脑风扇。第一版只支持手动启动，不安装开机自启服务；`run` 是无需交互的入口，留待以后接入 macOS LaunchAgent 或 Windows 任务计划程序。

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

探针应输出含 `temperature_c` 的 JSON。如果探针无法读取 CPU 温度，先检查 Windows 传感器可用性和权限。`check` 成功后再运行 `run`；按 `Ctrl+C` 停止。停止后净化器保持当时的电源和档位状态。

## 配置与注意事项

`config.example.toml` 是可复制的起点。`token_file` 相对 `config.toml` 所在目录解析，默认是 `.secrets/purifier-token`。`platform` 只接受与当前电脑相符的 `macos` 或 `windows`。`temperature_sensor` 当前只支持 `cpu`。默认每 5 秒采样一次；阈值要求低温恢复值小于高温触发值，低级别小于高级别，级别范围为 0–17。

净化器 IP 默认 `192.168.250.118`。如果路由器重新分配地址，请更新 `[purifier].host`。局域网或温度探针暂时不可用时，程序会报告故障并重试；遇到设备拒绝级别时应停止运行并核对可用档位。`check` 报型号不符时请勿运行控制程序。

macOS 的 `check` 已只读实测。低级别 3 和高级别 17 尚未在这台净化器上写入并读回验证；请在能观察设备、能恢复原状态时短时验收，在确认前不要无人看护地运行高温联动。Windows 真机传感器与净化器联动也尚需在 Windows 电脑上验收。
