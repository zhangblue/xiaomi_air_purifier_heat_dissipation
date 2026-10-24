# 跨平台目录包指南实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将 macOS、Windows x64、Linux x86_64 打包方法集中到 `docs/bundle-build.md`，并以 Mac 上的 Linux amd64 容器构建为重点。

**架构：** README 仅保留打包入口和兼容性摘要，新指南承担全部平台构建命令及目录包迁移说明。现有 macOS 故障排查页保留并修正相对链接；文档静态测试保护命令、链接与私有数据隔离约束。

**技术栈：** Markdown、Python `unittest`、Python 3.11、PyInstaller 6、OrbStack/Docker CLI、Debian bookworm Linux amd64 容器。

---

## 文件职责

- `docs/bundle-build.md`（新建）：三个平台的完整打包指南，尤其是 Mac 容器内构建 Linux x86_64、迁移与验证边界。
- `README.md`（修改）：保留简短打包摘要与通向新指南的链接，删除重复打包命令和旧 Linux 构建段；源码安装与运行段保留。
- `docs/macos-bundle-build.md`（修改）：把指向 README 旧锚点的链接改到新指南。
- `tests/test_bundle.py`（修改）：将现有 Linux 文档断言指向新指南，增加三平台、Mac 容器安全步骤和 README/排障页链接断言。

### 任务 1：编写唯一的跨平台打包指南

**文件：** `docs/bundle-build.md`、`tests/test_bundle.py`

- [ ] **步骤 1：写失败测试。** 在 `LinuxDocumentationTests` 中把原来针对 README 的 Linux 内容断言改为针对 `docs/bundle-build.md`；增加一个 `BundleGuideDocumentationTests`，读取同一文件，断言三个平台标题、`python -m tools.build_bundle`、`--platform linux/amd64`、公开源码 allowlist、`gcc libc6-dev`、只读 `--help`、`check.sh`/`run.sh`、不带 token/私有配置、不可覆盖输出目录。测试应检查关键事实，不钉死整段措辞。

  ```python
  root = Path(__file__).resolve().parents[1]
  guide = (root / "docs" / "bundle-build.md").read_text(encoding="utf-8")
  for text in ("macOS", "Windows x64", "Linux x86_64", "--platform linux/amd64",
               "gcc libc6-dev", "pyproject.toml config.example.toml src tools README.md tests"):
      self.assertIn(text, guide)
  ```
- [ ] **步骤 2：验证红灯。** 运行 `/Users/zhangdi/works/workspace/github/xiaomi_air_purifier_heat_dissipation/.venv/bin/python -m unittest tests.test_bundle.LinuxDocumentationTests tests.test_bundle.BundleGuideDocumentationTests -v`，预期因新指南不存在而失败；不得连接净化器。
- [ ] **步骤 3：最小文档实现。** 新指南先写共同安全与输出规则，再写 macOS arm64（核验过的 `smctemp` 0.7.0、Python 3.11）、Windows x64（Python 3.11、.NET 8 SDK）、Linux x86_64 原生构建（Python 3.11）、Mac 容器构建 Linux x86_64。Mac 流程：`mktemp -d`；`tar` 仅复制 `pyproject.toml config.example.toml src tools README.md tests`；`docker build --platform linux/amd64 -t purifier-build-linux-x86_64 - <<'DOCKERFILE'`，Dockerfile 使用 `python:3.11-slim-bookworm` 并安装 `gcc libc6-dev`；`docker run --rm --platform linux/amd64 --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$BUNDLE_STAGE:/work" -w /work ...` 安装 `.[bundle]`、跑 `unittest`、运行 `python -m tools.build_bundle`；再用 Linux amd64 容器只读执行 `app/purifier-control --help`，最后 `ditto` 整个目录到一个尚不存在的 `dist/` 子目录。不得挂载整个仓库或复制 `config.toml`、`.secrets`、`.git`、`.venv`。解释 Docker Desktop 可代替 OrbStack，但命令要求 Docker 引擎已启动；Mac Python 不能直接产出 Linux 包。

  ```sh
  set -o pipefail
  BUNDLE_STAGE="$(mktemp -d /tmp/purifier-mac-linux.XXXXXX)"
  tar --exclude='__pycache__' --exclude='*.pyc' --exclude='*.egg-info' \
    -cf - pyproject.toml config.example.toml src tools README.md tests |
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
- [ ] **步骤 4：补齐目标机与错误边界。** 保留原 README 中的目录包目标机 IP/token 配置、`check` 先于 `run`、停止不恢复设备、Linux `coretemp` `Package id N` 前提、Windows PawnIO 风险、macOS `smctemp` GPL 材料提示；解释 glibc/旧版 Linux 兼容限制。只读 `--help` 验证不等于净化器连接或真实温控验收。
- [ ] **步骤 5：验证与提交。** 运行 `python -m unittest tests.test_bundle -v` 与 `git diff --check`；仅提交 `docs/bundle-build.md`、`tests/test_bundle.py`，提交信息 `docs: add cross-platform bundle guide`。

### 任务 2：README 入口与现有排障链接

**文件：** `README.md`、`docs/macos-bundle-build.md`、`tests/test_bundle.py`

- [ ] **步骤 1：写失败测试。** 在 `BundleGuideDocumentationTests` 增加 README 相对链接和 macOS 排障页相对链接检查，并确保 README 不再出现旧的完整打包命令段；保留源码安装运行章节。

  ```python
  root = Path(__file__).resolve().parents[1]
  readme = (root / "README.md").read_text(encoding="utf-8")
  troubleshooting = (root / "docs" / "macos-bundle-build.md").read_text(encoding="utf-8")
  self.assertIn("[跨平台打包指南](docs/bundle-build.md)", readme)
  self.assertIn("bundle-build.md", troubleshooting)
  self.assertNotIn("macOS 或 Windows 不能生成 Linux 包", readme)
  ```
- [ ] **步骤 2：验证红灯。** 运行 `python -m unittest tests.test_bundle.BundleGuideDocumentationTests -v`，预期新增链接或去重断言失败。
- [ ] **步骤 3：最小文档修改。** README 的“构建与迁移目录包”缩为目标机兼容性摘要和 `[跨平台打包指南](docs/bundle-build.md)` 链接，删除该节原有 macOS/Windows 构建命令、目录包配置命令及独立 Ubuntu 构建段；保留后面的源码安装运行、配置、验收历史和 token 获取章节。macOS 排障页两个旧 README 锚点改为新指南链接；排障步骤本身不变。避免 README 再声称 Mac 不能通过容器编 Linux 包。
- [ ] **步骤 4：完整验证与提交。** 运行 `/Users/zhangdi/works/workspace/github/xiaomi_air_purifier_heat_dissipation/.venv/bin/python -m unittest discover -s tests -v`、`git diff --check`、`git status --short`；仅提交上述三个文件，提交信息 `docs: link README to bundle guide`。不得暂存本机 `config.toml`、`.secrets` 或无关产物。
