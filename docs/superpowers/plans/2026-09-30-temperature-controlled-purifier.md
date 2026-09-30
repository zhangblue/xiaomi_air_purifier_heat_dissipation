# 电脑温度联动净化器实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在 macOS 和 Windows 上通过手动启动的同一套程序读取 CPU 温度，并按配置调整 AC-M3-CA 净化器的最爱档级别。

**架构：** Python 主程序负责 TOML 配置、温度规则、局域网控制和运行循环；平台采集器提供统一的摄氏温度接口。macOS 调用 `smctemp`，Windows 调用基于 LibreHardwareMonitor 的 .NET 辅助程序。控制器仅在目标级别变化时写入净化器，网络失败后读取设备实际状态再重试。

**技术栈：** Python 3.11、标准库 `tomllib`/`unittest`、`python-miio`、macOS `smctemp`、Windows .NET 8 + `LibreHardwareMonitorLib` 0.9.6。

---

## 前提与文件结构

本目录目前不是 Git 仓库，尚无可用 worktree。实施时先在此目录初始化 Git 并保存现有设计和计划，再为代码开发建立隔离工作区；若用户指定已有仓库，改用该仓库。密钥文件 `.secrets/purifier-token` 已存在且权限为 `0600`，不得提交、打印或复制到测试夹具。`/.secrets/` 已写入 `.gitignore`。

计划创建以下文件，每个文件只负责一项明确工作：

| 文件 | 职责 |
| --- | --- |
| `pyproject.toml` | Python 包、运行依赖、命令入口和测试配置。 |
| `config.example.toml` | 不含密钥的 macOS 示例；Windows 用户只改 `platform` 和采集器路径。 |
| `src/purifier_control/config.py` | 读取、解析和验证配置；相对 token 路径基于配置文件目录解析。 |
| `src/purifier_control/policy.py` | 60/55°C 滞回与持续时间规则，纯函数式状态机。 |
| `src/purifier_control/sensors.py` | 温度采集接口、macOS `smctemp` 与 Windows 辅助程序输出解析。 |
| `src/purifier_control/purifier.py` | `python-miio` 设备状态读取、型号核对、开机和最爱档级别写入。 |
| `src/purifier_control/runner.py` | 采样循环、设备状态协调、重试与日志。 |
| `src/purifier_control/cli.py` | `check`（只读）和 `run`（持续控制）命令入口。 |
| `windows/TemperatureProbe/TemperatureProbe.csproj`、`Program.cs` | Windows CPU 温度 JSON 辅助程序。 |
| `windows/TemperatureProbe.Tests/` | 传感器选择与无效读数测试。 |
| `tests/test_config.py`、`test_policy.py`、`test_sensors.py`、`test_purifier.py`、`test_runner.py` | Python 单元与组合测试。 |
| `README.md` | macOS/Windows 安装、手动启动、密钥放置、权限、故障排查和真机验收。 |

依赖依据：[python-miio 净化器接口](https://python-miio.readthedocs.io/en/latest/_modules/miio/integrations/zhimi/airpurifier/airpurifier.html)、[smctemp](https://github.com/narugit/smctemp)、[LibreHardwareMonitor 官方集成示例](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor#integrate-the-library-in-own-application)、[NuGet 包](https://www.nuget.org/packages/LibreHardwareMonitorLib/)。Windows SDK 不在当前 Mac 上，Windows 构建与真机采集须在 Windows 环境验证。

## 任务 1：配置与密钥读取

**交付物：** 能在两个平台解析相同字段、阻止错误配置和密钥泄露的 `AppConfig`。

**文件：** 创建 `pyproject.toml`、`config.example.toml`、`src/purifier_control/__init__.py`、`src/purifier_control/config.py`、`tests/test_config.py`。

- [ ] **步骤 1：写失败测试。** `tests/test_config.py` 用 `tempfile.TemporaryDirectory()` 建临时配置和 token 文件；把系统平台检测注入或 mock 为对应值，分别验证 `platform=macos/windows` 合法、与当前系统不匹配和 `auto` 非法；`low_favorite_level=3`、`high_favorite_level=17` 合法，相反次序非法；`recover_temperature_c < high_temperature_c`；相对 `token_file` 按配置目录解析；token 必须恰好是 32 个十六进制字符且不会出现在错误消息中。关键断言：

  ```python
  with self.assertRaisesRegex(ValueError, "platform"):
      load_config(path_with_platform_auto)
  self.assertEqual(load_config(valid_path).purifier.host, "192.168.250.118")
  self.assertNotIn(secret_value, str(caught.exception))
  ```

- [ ] **步骤 2：运行测试确认失败。** `python3 -m unittest tests.test_config -v` 应因模块或 `load_config` 未定义而失败。
- [ ] **步骤 3：实现最少代码。** `load_config(path: Path, running_platform: str | None = None) -> AppConfig` 用 `tomllib.load` 读取配置，创建不可变 dataclass；`platform` 仅允许 `macos/windows`，并与传入平台或 `sys.platform` 比较；检查阈值、正数持续时间、`0 <= low < high <= 17`。用 `Path(path).parent / token_file` 解析密钥位置，读取时 `strip()`，只在内存中传给适配器。异常只报告字段名、路径和原因，不包含 token 内容。`pyproject.toml` 声明 Python 3.11 和 `python-miio==0.5.12`；macOS 现有系统 Python 为 3.9，实施时用已安装的 `uv` 建 Python 3.11 虚拟环境。

  ```python
  @dataclass(frozen=True)
  class ControlConfig:
      high_temperature_c: float
      high_duration_seconds: float
      recover_temperature_c: float
      recover_duration_seconds: float
      high_favorite_level: int
      low_favorite_level: int
  ```

- [ ] **步骤 4：运行测试。** `python3 -m unittest tests.test_config -v` 全部通过；查看 `config.example.toml` 只包含 `token_file = ".secrets/purifier-token"`，没有真实 token。
- [ ] **步骤 5：提交。** 在已初始化的 Git 仓库中只添加此任务文件；检查 `git status --short` 和 `git diff --cached --check`，确认 `.secrets/` 未被暂存后提交。

## 任务 2：纯规则引擎

**交付物：** 不连接设备也能精确判断何时切换级别的状态机。

**文件：** 创建 `src/purifier_control/policy.py`、`tests/test_policy.py`。

- [ ] **步骤 1：写失败测试。** 使用人工时间戳验证：启动目标为低级别；`60.0` 不升档；`60.1` 从 `t=0` 持续到 `t=15` 才升档；高温中途回到 `60.0` 会重置计时；处于高级别时 `55.0` 不降档，`54.9` 从 `t=0` 持续到 `t=120` 才降档；`None`、`NaN`、无穷大不引起转换且中断连续计时；55–60°C 保持原状态。关键断言：

  ```python
  policy = TemperaturePolicy(control_config)
  self.assertEqual(policy.current_level, 3)
  self.assertIsNone(policy.observe(60.1, 0.0))
  self.assertEqual(policy.observe(60.1, 15.0), 17)
  ```

- [ ] **步骤 2：运行 `python3 -m unittest tests.test_policy -v`，确认因 `TemperaturePolicy` 缺失而失败。**
- [ ] **步骤 3：实现 `TemperaturePolicy.observe(temperature_c: float | None, now: float) -> int | None`。** 返回值只在目标级别变化时为新级别，否则为 `None`。保存 `current_level`、`candidate_since`、`candidate_direction`；每次不符合候选条件或读数无效时清空候选。使用单调时钟输入，拒绝倒退时间戳。
- [ ] **步骤 4：运行该测试文件并确认通过。**
- [ ] **步骤 5：按任务 1 的密钥暂存检查方式提交本任务两个文件。**

## 任务 3：净化器局域网适配

**交付物：** 通过真实库控制 `zhimi.airpurifier.v6`，通过假设备验证命令顺序和失败路径。

**文件：** 创建 `src/purifier_control/purifier.py`、`tests/test_purifier.py`；修改 `pyproject.toml` 加入 `python-miio` 依赖。

- [ ] **步骤 1：写失败测试。** 使用记录调用的假设备：内部型号不为 `zhimi.airpurifier.v6` 时抛错且不写命令；启动时按 `on → set_favorite_level(3) → set_mode(Favorite) → status`；升温只需 `set_favorite_level(17)` 并读回；库抛异常时不记录成功，不输出 token；读回级别或模式不符时报错。

  ```python
  adapter = MiioPurifier(fake_device, expected_model="zhimi.airpurifier.v6")
  adapter.start(3)
  self.assertEqual(fake_device.calls[:3], ["on", ("level", 3), ("mode", "favorite")])
  ```

- [ ] **步骤 2：运行 `python3 -m unittest tests.test_purifier -v`，确认失败。**
- [ ] **步骤 3：实现 `MiioPurifier`。** 构造真实设备时使用 `miio.AirPurifier(host, token)`；连接时通过 `info().model` 核对型号。使用 `on()`、`set_favorite_level(level)`、`set_mode(OperationMode.Favorite)`、`status()`；核对 `status().is_on`、`status().mode`、`status().favorite_level`。把库异常包装成不含 token 的领域错误。
- [ ] **步骤 4：运行测试并检查 `python-miio` 实际导入路径与上述 API。** 若导入路径不同，按已安装版本的公开 API 调整适配器和测试，再运行完整测试。
- [ ] **步骤 5：提交适配器、测试和依赖声明。** 不在自动测试中写真实设备。

## 任务 4：macOS 与 Windows 温度采集

**交付物：** 两个平台均返回有限的摄氏温度，采集失败时明确报错。

**文件：** 创建 `src/purifier_control/sensors.py`、`tests/test_sensors.py`、`windows/TemperatureProbe/TemperatureProbe.csproj`、`windows/TemperatureProbe/Program.cs`、`windows/TemperatureProbe.Tests/TemperatureProbe.Tests.csproj`、`windows/TemperatureProbe.Tests/SensorSelectionTests.cs`。

- [ ] **步骤 1：写 Python 失败测试。** 假 `subprocess.run` 返回 `64.2\n` 时 macOS 采集器返回 `64.2`；非零退出码、空输出、`NaN`、负数或超过 `125°C` 报 `SensorError`；Windows JSON `{"temperature_c":64.2}` 成功，字段缺失或格式错误失败；命令使用绝对路径且设置超时，不经 shell。
- [ ] **步骤 2：运行 `python3 -m unittest tests.test_sensors -v`，确认失败。**
- [ ] **步骤 3：实现 Python 采集器。** 定义 `TemperatureSource.read() -> float`；macOS 用 `subprocess.run([smctemp_path, "-c"], capture_output=True, text=True, timeout=...)`；Windows 用 `[probe_path, "--json"]`。统一校验有限数值和合理区间，不把失败伪装为 0°C。
- [ ] **步骤 4：实现 Windows 辅助程序。** .NET 8 项目引用 `LibreHardwareMonitorLib` 0.9.6。使用 `Computer { IsCpuEnabled = true }`、`Open()` 和下面的 `UpdateVisitor` 更新 CPU 硬件。只选 `SensorType.Temperature`：优先名称为 `CPU Package` 的有效值；否则用 CPU Core 温度的平均值；找不到则以非零退出码和不含敏感信息的错误消息结束。成功时标准输出只有单行 `{"temperature_c":64.2}`。`finally` 调用 `Close()`。

  ```csharp
  using LibreHardwareMonitor.Hardware;
  public sealed class UpdateVisitor : IVisitor {
      public void VisitComputer(IComputer computer) => computer.Traverse(this);
      public void VisitHardware(IHardware hardware) {
          hardware.Update();
          foreach (var child in hardware.SubHardware) child.Accept(this);
      }
      public void VisitSensor(ISensor sensor) { }
      public void VisitParameter(IParameter parameter) { }
  }
  public sealed record SensorReading(string Name, float? Value);
  ```

- [ ] **步骤 5：在 Windows 测试项目验证传感器筛选。** 用抽出的 `SelectCpuTemperature(IEnumerable<SensorReading>)` 测试 Package 优先、Core 平均、无效值排除和无传感器报错；在 Windows 执行 `dotnet test windows/TemperatureProbe.Tests/TemperatureProbe.Tests.csproj`，预期全通过。当前 Mac 上无法以真实 Windows 传感器替代这一步。
- [ ] **步骤 6：运行 Python 采集测试及 macOS 真机读取。** `python3 -m unittest tests.test_sensors -v` 通过；安装 `smctemp` 后运行 `smctemp -c`，确认输出有效温度。Windows 上运行已构建的辅助程序确认 JSON 格式。
- [ ] **步骤 7：提交采集器、辅助程序和测试。** 不提交 Windows 构建产物。

## 任务 5：运行循环、命令入口与恢复

**交付物：** 用户能手动检查环境并持续运行；断网、传感器错误和手动停止都有确定行为。

**文件：** 创建 `src/purifier_control/runner.py`、`src/purifier_control/cli.py`、`tests/test_runner.py`；修改 `pyproject.toml` 添加 `purifier-control` 命令入口。

- [ ] **步骤 1：写失败测试。** 假采集器、假净化器与可控单调时钟验证：启动时应用低级别；每 5 秒采样；第 15 秒升温命令仅发一次；第 120 秒降温命令仅发一次；传感器错误保留当前级别；网络连接失败采用有限退避，恢复后读取实际状态再协调；`check` 只读取设备与传感器，不调用开机或设置级别；`KeyboardInterrupt` 退出时不关闭净化器。
- [ ] **步骤 2：运行 `python3 -m unittest tests.test_runner -v`，确认失败。**
- [ ] **步骤 3：实现 `Runner.tick(now)` 和 `Runner.run()`。** `tick` 读取温度并交给 `TemperaturePolicy.observe`；在 `desired_level` 中保留规则引擎当前目标，设备成功读回前不清除待写入目标。连接失败时按 5、10、20、30 秒封顶重试；恢复后重新读取设备状态，并将实际级别与 `desired_level` 对齐。`run` 用 `time.monotonic()`、配置的采样间隔和可中断等待。`check` 只做配置/传感器/设备信息读取。
- [ ] **步骤 4：实现 CLI。** `purifier-control --config config.toml check` 输出平台、温度、IP、内部型号及连接状态，但不输出 token；`purifier-control --config config.toml run` 手动启动持续控制。日志只写状态变化、失败与恢复；不得记录库对象或完整配置对象。
- [ ] **步骤 5：运行完整 Python 测试。** `python3 -m unittest discover -s tests -v` 全通过；停止命令后确认程序不发送关机操作。
- [ ] **步骤 6：提交运行循环、入口和测试。**

## 任务 6：文档与真机验收

**交付物：** 用户能在 macOS 或 Windows 安装、配置并手动运行；AC-M3-CA 的级别和 token 经只读/受控检查确认。

**文件：** 创建 `README.md`；修改 `config.example.toml` 和必要的错误说明。

- [ ] **步骤 1：写 README。** macOS 用 Python 3.11 和 `smctemp`；Windows 用 Python 3.11、.NET 8 与发布好的 TemperatureProbe。分别给出复制示例配置、填写 `platform`、放置私有 token 文件、运行 `check`、运行 `run`、按 Ctrl+C 停止的完整命令。明确第一版不自启、程序停止不关净化器、净化器不替代电脑散热。
- [ ] **步骤 2：执行只读检查。** `check` 应显示本机 CPU 温度、`192.168.250.118`、`zhimi.airpurifier.v6`；不显示 token，且净化器状态不因 `check` 改变。
- [ ] **步骤 3：在用户可观察的真机测试中验证级别。** 记录原设备状态。先用临时配置把高温阈值设为高于当前 CPU 温度，启动程序并确认低级别 `3`；再把高温阈值设为低于当前 CPU 温度、恢复阈值进一步降低，重新启动并在 15 秒后确认高级别 `17`。两次都读回实际级别；若 `17` 被拒绝，找出设备实际可接受最高级别并更新配置与文档。测试结束按用户希望恢复的原状态设置设备；不在无人确认的情况下持续满速运行。
- [ ] **步骤 4：运行最终检查。** `python3 -m unittest discover -s tests -v`、Windows `dotnet test`、`git diff --check`；人工核对 `.secrets/` 未暂存，日志不含 token，文档与实际命令一致。
- [ ] **步骤 5：提交 README 与示例配置。** 交付 macOS 已实测、Windows 已测试的证据；若暂时没有 Windows 主机，明确列出 Windows 真机验证尚未完成，不宣称双平台全通过。

## 规格覆盖自检

- 手动启动且为未来自启保留无交互入口：任务 5、6。
- 仅 `macos/windows` 配置、两平台 CPU 采集：任务 1、4。
- 60°C/15 秒与 55°C/120 秒、最爱档 3/17 可配置：任务 1、2、3、5。
- AC-M3-CA、`zhimi.airpurifier.v6`、`192.168.250.118` 与私有 token：任务 1、3、6。
- 网络/传感器失败、手动改档、停止后不关机：任务 3、5、6。
