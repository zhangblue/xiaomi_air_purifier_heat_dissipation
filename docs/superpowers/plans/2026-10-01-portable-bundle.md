# 可迁移目录包实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在 Windows x64 与 macOS 原生架构上分别构建可复制运行的目录包，目标机不需要 Python、.NET Runtime 或 `smctemp` 安装，且包内绝不含 token。

**架构：** `tools/build_bundle.py` 负责预检、外部构建和原子发布；`tools/packaged_entry.py` 是 PyInstaller 入口。生成的启动脚本只设置包内 `bin/` 的 `PATH`，并向现有 CLI 传入包内 `config.toml`。Windows 自包含发布温度探针，macOS 收集并验证 `smctemp`。

**技术栈：** Python 3.11、PyInstaller 单目录模式、.NET 8 自包含发布、`unittest`、现有 `purifier-control` CLI。

---

## 文件职责

- 创建 `tools/build_bundle.py`：构建命令、平台预检、临时目录、目录内容、拒绝覆盖和发布。
- 创建 `tools/packaged_entry.py`：只调用 `purifier_control.cli.main()` 的冻结入口。
- 创建 `tests/test_bundle.py`：使用临时目录和替身外部命令检查构建器行为，不访问真实设备。
- 修改 `pyproject.toml`：声明单独的打包依赖组，不改变运行时依赖。
- 修改 `README.md`：说明构建命令、目标机使用和不可消除的硬件/系统前提。
- 修改 `.gitignore`（若已存在）或创建它：忽略 `dist/` 与本地打包缓存；保留已有密钥忽略规则。

## 任务 1：安全的构建骨架与目录清单

**文件：** 创建 `tools/build_bundle.py`、`tools/packaged_entry.py`、`tests/test_bundle.py`；修改 `pyproject.toml`、`.gitignore`。

- [ ] **步骤 1：编写失败的目录和密钥排除测试。** 在 `tests/test_bundle.py` 中构造临时项目，放置 `config.example.toml`、`config.toml`、`.secrets/purifier-token`，通过依赖注入的构建命令替身创建假 `app/purifier-control`；断言最终目录只有声明的文件，`config.toml` 与 `.secrets` 不存在，Windows 模板含 `platform = "windows"`。

  ```python
  # 核心断言；测试夹具中的 token 使用固定的非真实字符串。
  result = build_bundle(source, output, "macos", machine_arch, run_command=fake_run)
  assert (result / "config.example.toml").is_file()
  assert not (result / "config.toml").exists()
  assert not (result / ".secrets").exists()
  assert "0123456789abcdef0123456789abcdef" not in "".join(
      p.read_text() for p in result.rglob("*") if p.is_file() and p.suffix in {".toml", ".txt", ".command"})
  ```
- [ ] **步骤 2：验证红灯。** 运行 `.venv/bin/python -m unittest tests/test_bundle.py -v`；预期因为 `tools.build_bundle` 不存在而失败。
- [ ] **步骤 3：实现最小构建 API。** 入口 `build_bundle(source: Path, output: Path, platform: str, arch: str, *, run_command: Callable[[list[str]], None]) -> Path`；用 `sys.platform` 与 `platform.machine()` 核对目标；只从白名单复制模板、写启动脚本和说明文件；临时目录建在输出父目录，所有步骤成功才 `rename` 到最终目录；若输出已存在则拒绝，不删除或覆盖。

  ```python
  if output.exists():
      raise FileExistsError(f"bundle output already exists: {output}")
  with tempfile.TemporaryDirectory(prefix=".bundle-", dir=output.parent) as temporary:
      staging = Path(temporary) / "bundle"
      staging.mkdir()
      # 此处只从明确列出的公开文件生成内容，不遍历 source。
      shutil.copyfile(source / "config.example.toml", staging / "config.example.toml")
      staging.rename(output)
  return output
  ```
- [ ] **步骤 4：验证绿灯与边界。** 运行 `.venv/bin/python -m unittest tests/test_bundle.py -v`；增加并运行输出已存在、错误平台、外部命令失败时无最终包的测试。检查包内文件内容未含测试 token 字符串。
- [ ] **步骤 5：提交。** 运行完整 Python 测试和 `git diff --check` 后，仅暂存任务文件，提交 `feat: add secure portable bundle skeleton`。

## 任务 2：PyInstaller 和 macOS 温度程序

**文件：** 修改 `tools/build_bundle.py`、`tests/test_bundle.py`、`pyproject.toml`。

- [ ] **步骤 1：写失败测试。** 使用替身命令断言构建器以当前 Python 运行 `PyInstaller --onedir --console`，构建入口为 `tools/packaged_entry.py`，并把其输出移入 `app/`；模拟 `smctemp` 依赖文件，断言它们出现在 `bin/` 且启动脚本仅在当前进程设置 `PATH`。

  ```python
  pyinstaller_calls = [args for args in calls if args[:3] == [sys.executable, "-m", "PyInstaller"]]
  assert len(pyinstaller_calls) == 1
  assert "--onedir" in pyinstaller_calls[0]
  assert "--name" in pyinstaller_calls[0]
  assert "purifier-control" in pyinstaller_calls[0]
  ```
- [ ] **步骤 2：验证红灯。** 运行 `.venv/bin/python -m unittest tests/test_bundle.py -v`，确认新断言因尚未调用 PyInstaller / 收集 `smctemp` 而失败。
- [ ] **步骤 3：实现最少代码。** 从 `sys.executable -m PyInstaller` 调用单目录构建，固定 `--distpath` / `--workpath` / `--specpath` 到临时目录。macOS 用 `shutil.which("smctemp")` 定位文件；用 `otool -L` 检查动态库。首版只接受系统库依赖（本机 `smctemp` 当前仅依赖 IOKit、libc++、libSystem），遇到非系统库则明确报错，避免仅复制库却未修正加载路径的伪便携包；缺少许可证材料时也报错。保持构建命令为参数数组，不使用 `shell=True`。

  ```python
  run_command([sys.executable, "-m", "PyInstaller", "--onedir", "--console",
               "--name", "purifier-control", "--distpath", str(dist_path),
               "--workpath", str(work_path), "--specpath", str(spec_path),
               str(source / "tools" / "packaged_entry.py")])
  ```
- [ ] **步骤 4：验证绿灯并做本机冒烟。** 运行单元测试和完整 Python 测试；在 macOS 安装打包依赖后生成真实目录，在隔离路径运行 `app/purifier-control --help` 与打包的 `smctemp -c`，不运行真实 `run`。
- [ ] **步骤 5：提交。** `git diff --check` 后提交 `feat: bundle macOS runtime and temperature probe`。

## 任务 3：Windows 自包含探针与启动器

**文件：** 修改 `tools/build_bundle.py`、`tests/test_bundle.py`。

- [ ] **步骤 1：写失败测试。** 模拟 Windows 平台，断言构建命令包含 `dotnet publish windows/TemperatureProbe/TemperatureProbe.csproj -c Release -r win-x64 --self-contained true -o <临时目录>`；发布目录整体进入包内 `bin/`，`.cmd` 调用 `app\purifier-control.exe --config <包目录>\config.toml check|run`。

  ```python
  publish = next(args for args in calls if args[:2] == ["dotnet", "publish"])
  assert publish[publish.index("-r") + 1] == "win-x64"
  assert publish[publish.index("--self-contained") + 1] == "true"
  assert '"%~dp0app\\purifier-control.exe"' in (output / "check.cmd").read_text()
  ```
- [ ] **步骤 2：验证红灯。** 运行 `.venv/bin/python -m unittest tests/test_bundle.py -v`，确认缺少 Windows 发布调用/脚本时失败。
- [ ] **步骤 3：实现最少代码。** 为 Windows x64 添加 `dotnet` 预检、自包含发布和 `TemperatureProbe.exe` 存在性检查；生成 `check.cmd` / `run.cmd`，使用 `%~dp0` 定位包目录且只在脚本子进程扩展 `PATH`。不复制 SDK 或构建缓存。

  ```python
  run_command(["dotnet", "publish", str(source / "windows/TemperatureProbe/TemperatureProbe.csproj"),
               "-c", "Release", "-r", "win-x64", "--self-contained", "true",
               "-o", str(probe_output)])
  if not (probe_output / "TemperatureProbe.exe").is_file():
      raise RuntimeError("TemperatureProbe.exe is missing from published output")
  ```
- [ ] **步骤 4：验证绿灯及 Windows 构建。** 运行 Python 测试；在 Windows 构建机执行 `dotnet test windows/TemperatureProbe.Tests/TemperatureProbe.Tests.csproj`，生成目录后运行包内 `purifier-control.exe --help` 与 `TemperatureProbe.exe --json`。如果当前会话无法在 Windows 上构建，就只报告模拟测试，不宣称 Windows 包已验证。
- [ ] **步骤 5：提交。** `git diff --check` 后提交 `feat: bundle self-contained Windows temperature probe`。

## 任务 4：使用文档与发布验证

**文件：** 修改 `README.md`、`tests/test_bundle.py`。

- [ ] **步骤 1：写失败测试。** 增加对生成 `README.txt` 的断言：含 `config.example.toml` 到 `config.toml` 的复制步骤、目标机 token 文件位置、只读 `check` 优先、Windows PawnIO 例外、macOS 安全提示、`run` 停止不恢复档位。

  ```python
  guide = (output / "README.txt").read_text(encoding="utf-8")
  for required in ("config.example.toml", "config.toml", ".secrets/purifier-token",
                   "check", "run", "PawnIO"):
      assert required in guide
  ```
- [ ] **步骤 2：验证红灯。** 运行 `.venv/bin/python -m unittest tests/test_bundle.py -v`，确认说明缺项被测试捕获。
- [ ] **步骤 3：实现文档与命令入口。** README 写出两平台构建示例、目录迁移步骤、同系统/同架构限制、未签名程序与驱动限制。构建器 CLI 接受 `--output`，默认 `dist/<platform>-<arch>`，输出成功路径；失败时给出不含密钥的诊断信息。

  ```python
  parser = argparse.ArgumentParser(prog="build_bundle")
  parser.add_argument("--output", type=Path)
  args = parser.parse_args()
  platform_name = "windows" if sys.platform == "win32" else "macos"
  output = args.output or Path("dist") / f"{platform_name}-{platform.machine().lower()}"
  ```
- [ ] **步骤 4：完整验证。** 运行 `.venv/bin/python -m unittest discover -s tests -v`、`git diff --check`；检查包目录不存在 `config.toml`、`.secrets/` 和 token 字符串。可用平台各自做离线冒烟；实际硬件 `run` 只按 `AGENTS.md` 的在场流程执行。
- [ ] **步骤 5：提交并交接。** 提交 `docs: explain portable bundle build and deployment`。说明已验证平台、未验证平台和任何第三方许可证/驱动限制；除非用户另行要求，不自动合并或推送。
