"""Safety checks for the portable directory bundle skeleton."""

from __future__ import annotations

import platform as platform_module
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.build_bundle import build_bundle


FAKE_TOKEN = "0123456789abcdef0123456789abcdef"


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "config.example.toml").write_text(
            'platform = "macos"\n[purifier]\ntoken_file = ".secrets/purifier-token"\n',
            encoding="utf-8",
        )
        (self.source / "config.toml").write_text(
            f'platform = "macos"\ntoken = "{FAKE_TOKEN}"\n', encoding="utf-8"
        )
        secrets = self.source / ".secrets"
        secrets.mkdir()
        (secrets / "purifier-token").write_text(FAKE_TOKEN, encoding="ascii")
        self.output = self.root / "dist" / "bundle"
        self.output.parent.mkdir()

    def fake_run(self, args):
        app = Path(args[-1])
        app.parent.mkdir(parents=True, exist_ok=True)
        app.write_text("fake executable", encoding="utf-8")

    def test_macos_bundle_contains_only_public_manifest(self):
        machine_arch = platform_module.machine()
        with patch("tools.build_bundle.sys.platform", "darwin"):
            result = build_bundle(self.source, self.output, "macos", machine_arch,
                                  run_command=self.fake_run)

        self.assertEqual(result, self.output)
        self.assertEqual(
            {str(path.relative_to(result)) for path in result.rglob("*")},
            {"app", "app/purifier-control", "bin", "config.example.toml",
             "check.command", "run.command", "README.txt"},
        )
        self.assertFalse((result / "config.toml").exists())
        self.assertFalse((result / ".secrets").exists())
        self.assertNotIn(
            FAKE_TOKEN,
            "".join(path.read_text(encoding="utf-8") for path in result.rglob("*")
                    if path.is_file()),
        )

    def test_windows_template_targets_windows(self):
        with patch("tools.build_bundle.sys.platform", "win32"), patch(
            "tools.build_bundle.platform_module.machine", return_value="AMD64"
        ):
            result = build_bundle(self.source, self.output, "windows", "x64",
                                  run_command=self.fake_run)
        self.assertIn('platform = "windows"',
                      (result / "config.example.toml").read_text(encoding="utf-8"))

    def test_existing_output_is_not_changed(self):
        self.output.mkdir()
        marker = self.output / "user-data.txt"
        marker.write_text("keep this", encoding="utf-8")
        with patch("tools.build_bundle.sys.platform", "darwin"):
            with self.assertRaises(FileExistsError):
                build_bundle(self.source, self.output, "macos", platform_module.machine(),
                             run_command=self.fake_run)
        self.assertEqual(marker.read_text(encoding="utf-8"), "keep this")

    def test_dangling_output_symlink_is_not_replaced(self):
        self.output.symlink_to(self.root / "missing-target", target_is_directory=True)
        with patch("tools.build_bundle.sys.platform", "darwin"):
            with self.assertRaises(FileExistsError):
                build_bundle(self.source, self.output, "macos", platform_module.machine(),
                             run_command=self.fake_run)
        self.assertTrue(self.output.is_symlink())

    def test_target_must_match_build_machine(self):
        with patch("tools.build_bundle.sys.platform", "darwin"):
            with self.assertRaises(ValueError):
                build_bundle(self.source, self.output, "windows", "x64",
                             run_command=self.fake_run)
        self.assertFalse(self.output.exists())

    def test_failed_external_build_does_not_publish_bundle(self):
        def fail(_args):
            raise RuntimeError("build failed")

        with patch("tools.build_bundle.sys.platform", "darwin"):
            with self.assertRaisesRegex(RuntimeError, "build failed"):
                build_bundle(self.source, self.output, "macos", platform_module.machine(),
                             run_command=fail)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.output.parent.iterdir()), [])

    def test_creates_new_dist_parent_for_first_build(self):
        output = self.root / "fresh-dist" / "macos-arm64"
        with patch("tools.build_bundle.sys.platform", "darwin"):
            result = build_bundle(self.source, output, "macos", platform_module.machine(),
                                  run_command=self.fake_run)
        self.assertTrue((result / "app" / "purifier-control").is_file())


if __name__ == "__main__":
    unittest.main()
