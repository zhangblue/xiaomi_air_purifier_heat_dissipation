# 跨平台目录包构建与迁移指南

## 共同规则与安全边界

在项目根目录执行构建。目录包只能迁移到同操作系统、同 CPU 架构的电脑，目标机无需另装 Python、Python 包、.NET Runtime 或 `smctemp`。目标机仍须有可读的 CPU 温度传感器，并能通过局域网连接净化器。目录包不安装开机自启服务。

构建成功会打印输出路径，现有输出目录不会被覆盖；自选 `--output` 也必须指定尚不存在的目录。请复制整个目录，不能只复制可执行文件。token 和私有配置不进入构建包；不要把 token 写进命令参数、日志、截图或提交。

macOS、Windows、Linux 包必须分别在对应系统和架构的环境中构建。Mac Python 不能直接产出 Linux 包；Mac 上可以借助 Linux 容器构建。较新系统构建的产物不保证兼容较旧系统；Linux 还受 glibc 版本限制，其他发行版、旧版 Linux、不同架构和非 glibc 系统需另行构建与验证。

## macOS arm64

构建机需要 Python 3.11、Homebrew 安装的 `narugit/tap/smctemp`。构建器仅接受核验过的 macOS arm64 `smctemp` 0.7.0 二进制，并核对来源归档、许可证材料和系统依赖。Homebrew 安装本身不保证命中白名单，核验失败会停止构建；其他架构或二进制需另行验证。

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[bundle]'
.venv/bin/python -m tools.build_bundle
# 自选尚不存在的输出目录：
# .venv/bin/python -m tools.build_bundle --output dist/my-mac
```

默认输出为 `dist/macos-<架构>/`。环境失效或 PyInstaller 构建失败时，参阅 [macOS 打包环境与故障排查](macos-bundle-build.md)。包内 `bin/` 随附 `smctemp` 的 GPL-2.0-only 许可证和固定版本源码归档，再分发时应查阅；随附材料不等同于法律审核。

## Windows x64

构建机需要 Python 3.11 和 .NET 8 SDK，在项目根目录的 PowerShell 执行：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[bundle]'
.\.venv\Scripts\python.exe -m tools.build_bundle
# 自选尚不存在的输出目录：
# .\.venv\Scripts\python.exe -m tools.build_bundle --output dist\my-pc
```

默认输出为 `dist/windows-x64/`。构建与目标机验收须在 Windows 上分别完成，macOS 的 Python 测试不能证明 Windows 验收通过。

## Linux x86_64 原生构建

支持目标为 Ubuntu 26.04 x86_64。使用 Linux x86_64 环境中的 Python 3.11，Ubuntu 系统 Python 可保持不变：

```sh
python3.11 -m venv .venv
.venv/bin/python -m pip install -e '.[bundle]'
.venv/bin/python -m tools.build_bundle
```

输出为 `dist/linux-x86_64/`。Ubuntu 26.04 是目标验收环境，离线测试通过不代表已完成 Ubuntu 构建、真实温度或设备连接验收。

## 在 Mac 容器中构建 Linux x86_64

使用 OrbStack 或 Docker Desktop 提供的 Docker 引擎，执行前须启动引擎。下面命令在 Mac 项目根目录执行，通过 `--platform linux/amd64` 选择 Linux x86_64；Apple Silicon 上可能需要模拟执行，速度较慢。

先用 `mktemp -d` 建立暂存目录，只按公开源码 allowlist 复制 `pyproject.toml config.example.toml src tools README.md tests docs`。公开 `docs/` 是文档测试的输入，须一同复制。不得挂载整个仓库，也不得复制 `config.toml`、`.secrets`、`.git`、`.venv`。构建目录不需要净化器 token，也不连接真实设备。

```sh
set -o pipefail
BUNDLE_STAGE="$(mktemp -d /tmp/purifier-mac-linux.XXXXXX)"
tar --exclude='__pycache__' --exclude='*.pyc' --exclude='*.egg-info' \
  -cf - pyproject.toml config.example.toml src tools README.md tests docs |
  tar -xf - -C "$BUNDLE_STAGE"

docker build --platform linux/amd64 -t purifier-build-linux-x86_64 - <<'DOCKERFILE'
FROM python:3.11-slim-bookworm
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
DOCKERFILE

docker run --rm --platform linux/amd64 --user "$(id -u):$(id -g)" \
  -e HOME=/tmp -v "$BUNDLE_STAGE:/work" -w /work purifier-build-linux-x86_64 \
  sh -lc 'python -m venv /tmp/buildvenv &&
    /tmp/buildvenv/bin/python -m pip install -e ".[bundle]" &&
    /tmp/buildvenv/bin/python -m unittest discover -s tests -v &&
    /tmp/buildvenv/bin/python -m tools.build_bundle'

docker run --rm --platform linux/amd64 -v "$BUNDLE_STAGE:/work:ro" \
  python:3.11-slim-bookworm \
  /work/dist/linux-x86_64/app/purifier-control --help
test ! -e dist/linux-x86_64-mac
ditto "$BUNDLE_STAGE/dist/linux-x86_64" dist/linux-x86_64-mac
```

逐步执行并检查退出状态；只有前一步成功才继续。尤其 `test ! -e` 失败时必须停止，换一个尚不存在的目标目录，避免 `ditto` 合并已有目录。保留 `$BUNDLE_STAGE` 可排查失败原因。镜像安装 `gcc libc6-dev` 供本机构建使用，目标机无需这些构建依赖。

第二次容器挂载使用 `:ro`，只读执行 `app/purifier-control --help`；它仅验证 Linux amd64 程序能启动并显示帮助，不等于净化器连接、真实温度或温控验收。最后复制到 Mac 的 `dist/linux-x86_64-mac` 仍然是 Linux 包，不能在 Mac 上运行。

## 目标机配置与验收

将整个包目录复制到目标机并进入该目录，把 `config.example.toml` 复制为 `config.toml`，修改 `[purifier].host`，确认 `platform` 与系统相符（`macos`、`windows` 或 `linux`）。`token_file` 相对配置文件目录解析，默认 `.secrets/purifier-token`。token 是设备的 32 位十六进制局域网密钥，只放在目标机私有文件中。

macOS：先把 token 复制到剪贴板，再执行以下命令；不要直接在终端粘贴 token。

```sh
cp config.example.toml config.toml
mkdir -p .secrets
chmod 700 .secrets
(umask 077; pbpaste > .secrets/purifier-token)
pbcopy < /dev/null
chmod 600 .secrets/purifier-token
./check.command
```

Windows PowerShell：先把 token 复制到剪贴板，再执行：

```powershell
Copy-Item .\config.example.toml .\config.toml
New-Item -ItemType Directory -Force .\.secrets | Out-Null
Get-Clipboard -Raw | Set-Content -NoNewline -Encoding ascii .\.secrets\purifier-token
Set-Clipboard -Value ''
.\check.cmd
```

在文件属性“安全”页确认 token 文件只对自己的 Windows 账户可读。程序去掉 token 首尾空白，`check` 会拒绝无效 token。

Linux：用文本编辑器创建只含 token 的 `.secrets/purifier-token`，再设置权限：

```sh
cp config.example.toml config.toml
mkdir -p .secrets
chmod 700 .secrets
# 用文本编辑器创建 .secrets/purifier-token 后设置权限
chmod 600 .secrets/purifier-token
./check.sh
```

Linux 目标机必须在 `/sys/class/hwmon` 提供可读的 `coretemp` CPU Package 传感器，标签格式为 `Package id N`；多个 Package 取最高温度。仅核心温度、AMD `k10temp` 或没有 Package 标签时不支持。缺失或无效温度会报错，首次有效温度前不会写入净化器；程序不安装驱动或修改内核配置。

先执行只读的 `check.sh`（Linux）、`check.command`（macOS）或 `check.cmd`（Windows），确认 CPU 温度可信、型号为 `zhimi.airpurifier.v6`、设备连接成功，再在场时手动运行 `run.sh`（Linux）、`run.command`（macOS）或 `run.cmd`（Windows）。Linux 执行 `./run.sh`，其他系统使用相应启动脚本。取得首次有效温度后程序会开机并设置低温最爱档。默认高于 60°C 持续 15 秒升至级别 17，低于 55°C 持续 120 秒降至级别 3。

按 `Ctrl+C` 停止；停止后不会恢复净化器原来的电源、模式或最爱档级别，需要自行恢复并读回确认。真实写控制验收须用户明确要求且在场：先只读记录原状态，短时测试后停止程序、恢复原状态并再次读回；恢复失败必须告知用户，不得声称通过。

macOS 未签名程序可能触发安全提示，由电脑所有者在系统设置批准运行。Windows 部分传感器需要管理员权限或单独安装 [PawnIO 官方签名驱动](https://github.com/namazso/PawnIO.Setup/releases)；驱动具有硬件访问权限，目录包不包含或安装驱动，由所有者决定是否安装，不应关闭内存完整性等安全保护。只有取得可信非零 CPU 温度且 `check` 成功后才运行控制。
