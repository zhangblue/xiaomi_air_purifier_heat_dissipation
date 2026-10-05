# macOS 打包环境与故障排查

以下命令均在项目根目录运行，仅用于构建 macOS 目录包，不会连接或控制净化器。构建机仍需满足 [README 的打包前提](../README.md#构建与迁移目录包)，包括 Python 3.11 和已核验的 `smctemp`。不要把 token 或私有 `config.toml` 放进打包命令。

如果运行 `python3.11 -m tools.build_bundle` 时看到 `Build failed: PyInstaller failed with exit code 1`，先检查使用的 Python 是否安装了 PyInstaller：

```sh
python3.11 -m PyInstaller --version
```

若提示 `No module named PyInstaller`，或项目现有的 `.venv/bin/python` 已失效，可在被 Git 忽略的 `.venv/` 内另建打包环境，不必删除旧环境：

```sh
python3.11 -m venv .venv/packaging
./.venv/packaging/bin/python -m pip install -e '.[bundle]'
./.venv/packaging/bin/python -m PyInstaller --version
./.venv/packaging/bin/python -m tools.build_bundle --output dist/macos-arm64-new
```

`--output` 后必须是尚不存在的目录；如果 `dist/macos-arm64-new` 已存在，请换一个新目录名。成功后将生成的**整个目录**复制到同系统、同 CPU 架构的目标电脑；目标机仍需按 [README 的目标机配置步骤](../README.md#目标机配置无需-python) 设置 IP 和 token，先运行包内只读的 `check.command`，确认无误后再手动运行 `run.command`。`run.command` 会在当前窗口持续运行，按 `Ctrl+C` 停止。

如果确认同一打包环境内已有 PyInstaller，但构建仍报同样错误，请保留完整错误信息继续排查；不要在日志中包含 token。
