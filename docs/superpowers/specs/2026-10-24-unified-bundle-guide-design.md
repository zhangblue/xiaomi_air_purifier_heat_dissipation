# 跨平台目录包指南设计

## 目标与边界

把 macOS、Windows x64 和 Linux x86_64 的目录包构建方法集中到单一文件 `docs/bundle-build.md`，并从 `README.md` 的打包入口链接过去。重点给出在 Apple Silicon Mac 上通过 Linux amd64 容器构建 Linux x86_64 包的可复现流程。只修改文档和必要的文档回归检查；不修改打包器、运行逻辑、配置默认值或真实设备状态。

## 文档结构

- `README.md` 的“构建与迁移目录包”缩为用途、兼容性边界和通向新指南的链接；移走平台构建命令及重复的目录包目标机配置说明。常规源码安装与运行章节保留。
- `docs/bundle-build.md` 是唯一详细入口：共同前提与安全规则、macOS arm64 原生构建、Windows x64 原生构建、Linux x86_64 原生构建、Mac 上构建 Linux x86_64、目录包迁移与只读检查、常见失败边界。
- 现有 `docs/macos-bundle-build.md` 继续承担 macOS 特定故障排查，修正其指向 README 旧锚点的链接，使其指向新指南。

## Mac 构建 Linux x86_64

明确区分“用 macOS Python 直接运行 PyInstaller”（不支持）与“在 Mac 上运行 Linux amd64 容器，容器内运行 PyInstaller”（支持）。说明需启动 OrbStack 或兼容的 Docker 引擎，使用 `--platform linux/amd64` 和 Python 3.11 的 Debian glibc 镜像。教程只把 `pyproject.toml`、`config.example.toml`、`src/`、`tools/`、`README.md` 和 `tests/` 复制到新建临时目录并挂载；不挂载整个仓库，以排除 `config.toml`、`.secrets/`、`.git/` 和本机虚拟环境。

已验证的 slim 镜像缺少编译 `netifaces` 所需的 `gcc`。指南应先在一次性 Linux amd64 构建镜像中安装 `gcc` 与 `libc6-dev`，再以宿主普通用户 UID/GID 安装 `.[bundle]`、运行离线测试、执行 `python -m tools.build_bundle`。生成包后先在 Linux amd64 容器里只读运行 `app/purifier-control --help`，再将整个目录复制到 Mac 项目的 `dist/` 下，目标路径若已存在则改用新名称，不覆盖旧包。可选地在 Ubuntu 宿主只读复核帮助入口；不得把帮助入口成功等同于净化器连接或温控实机验收。

## 其他平台与运行边界

macOS 构建继续要求 Python 3.11 和已核验的 `smctemp` 0.7.0；Windows 构建继续要求 Python 3.11 与 .NET 8 SDK。Linux 原生构建继续要求 Linux x86_64、Python 3.11 和 `.[bundle]`。所有目录包须整体迁移，目标机无须另装 Python；Windows 包的自包含温度探针不要求目标机 .NET Runtime。不同架构、较旧 Linux 或不同发行版的兼容性不作承诺，Linux 目标机还须提供可读的 `coretemp` `Package id N` 温度。

目录包不得携带 token、私有 `config.toml` 或 `.secrets/`。目标机自行配置 IP 和私有 token；先运行只读的 `check` 启动脚本，用户在场且确认状态后才手动运行 `run`。停止 `run` 不会恢复净化器原状态，首版不提供开机自启。指南不得把 Mac 容器测试写成 Ubuntu 设备连接或写控制已验收。

## 验证

核对 README、新指南和 macOS 故障排查的相对链接；检查新指南覆盖三个平台的构建命令和 Mac 容器完整步骤，README 不再保留相互矛盾的 Linux 编译说法。运行 `python -m unittest discover -s tests -v` 与 `git diff --check`。文档测试使用静态断言，不连接净化器；验收不要求重新执行真实设备写控制。
