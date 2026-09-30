# Final 定向修复报告

## 修复内容

- README 现在说明 macOS 目录包当前只接受已核验的 macOS arm64 `smctemp` 0.7.0 构建产物。
- README 明确说明 Homebrew 安装本身不保证命中二进制白名单，其他架构或不同二进制需另行验证，并将 arm64 构建机列为准备条件。
- 未放宽 `tools/build_bundle.py` 的代码核验。
- 在 `tests/test_bundle.py` 增加 README 回归检查，防止重新出现“macOS 为构建机原生架构”的宽泛承诺。

## 测试与检查

新增测试文件：`tests/test_bundle.py`，测试名 `test_readme_documents_verified_macos_bundle_architecture`。

定向测试命令：

```text
.venv/bin/python -m unittest tests.test_bundle.BundleTests.test_readme_documents_verified_macos_bundle_architecture -v
```

输出：`Ran 1 test ... OK`。

完整 Python 测试命令：

```text
.venv/bin/python -m unittest discover -s tests -v
```

输出：`Ran 89 tests ... OK`。

补丁空白检查命令：

```text
git diff --check
```

输出：无输出，退出码 0。

## 范围

仅更改 `README.md`、`tests/test_bundle.py` 和本报告。Minor TOCTOU 按裁定延期，本次未处理。未访问 token，也未连接真实设备。
