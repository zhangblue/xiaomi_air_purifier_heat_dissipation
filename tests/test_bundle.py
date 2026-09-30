"""Safety checks for the portable directory bundle skeleton."""

from __future__ import annotations

import hashlib
import json
import platform as platform_module
import sys
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
            'platform = "macos"\n'
            '[purifier]\n'
            'host = "192.168.250.118"\n'
            'token_file = ".secrets/purifier-token"\n'
            '[system]\n'
            'temperature_sensor = "cpu"\n'
            'sample_interval_seconds = 5\n'
            '[control]\n'
            'high_temperature_c = 60\n'
            'high_duration_seconds = 15\n'
            'recover_temperature_c = 55\n'
            'recover_duration_seconds = 120\n'
            'high_favorite_level = 17\n'
            'low_favorite_level = 3\n',
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
        keg = self.root / "Cellar" / "smctemp" / "0.7.0"
        (keg / "bin").mkdir(parents=True)
        self.smctemp = keg / "bin" / "smctemp"
        self.smctemp.write_text("fake smctemp", encoding="utf-8")
        (keg / "LICENSE").write_text("redistribution allowed", encoding="utf-8")
        (keg / ".brew").mkdir()
        (keg / "INSTALL_RECEIPT.json").write_text(json.dumps({
            "built_as_bottle": False,
            "poured_from_bottle": False,
            "source": {"tap": "narugit/tap", "versions": {"stable": "0.7.0"}},
            "arch": platform_module.machine(),
        }), encoding="utf-8")
        self.source_archive = self.root / "smctemp-0.7.0.tar.gz"
        self.source_archive.write_bytes(b"fixture smctemp source archive")
        source_hash = hashlib.sha256(self.source_archive.read_bytes()).hexdigest()
        binary_hash = hashlib.sha256(self.smctemp.read_bytes()).hexdigest()
        (keg / ".brew" / "smctemp.rb").write_text(
            'url "https://github.com/narugit/smctemp/archive/refs/tags/0.7.0.tar.gz"\n'
            f'sha256 "{source_hash}"\nlicense "GPL-2.0-only"\n', encoding="utf-8")
        source_patch = patch("tools.build_bundle.SMCTEMP_SOURCE_SHA256", source_hash,
                             create=True)
        source_patch.start()
        self.addCleanup(source_patch.stop)
        binary_patch = patch("tools.build_bundle.SMCTEMP_BINARY_SHA256",
                             {platform_module.machine(): binary_hash}, create=True)
        binary_patch.start()
        self.addCleanup(binary_patch.stop)
        license_patch = patch("tools.build_bundle.SMCTEMP_LICENSE_SHA256",
                              hashlib.sha256((keg / "LICENSE").read_bytes()).hexdigest(),
                              create=True)
        license_patch.start()
        self.addCleanup(license_patch.stop)
        which_patch = patch("shutil.which", return_value=str(self.smctemp))
        which_patch.start()
        self.addCleanup(which_patch.stop)
        self.calls = []

    def fake_run(self, args):
        self.calls.append(args)
        if args[0] == "otool":
            return (f"{self.smctemp}:\n"
                    "\t/System/Library/Frameworks/IOKit.framework/Versions/A/IOKit "
                    "(compatibility version 1.0.0, current version 1.0.0)\n"
                    "\t/usr/lib/libSystem.B.dylib "
                    "(compatibility version 1.0.0, current version 1.0.0)\n")
        if args == ["brew", "--cache", "smctemp"]:
            return str(self.source_archive) + "\n"
        if len(args) == 2 and Path(args[0]) == self.smctemp.resolve() and args[1] == "-v":
            return "0.7.0\n"
        if args[:3] == [sys.executable, "-m", "PyInstaller"]:
            dist = Path(args[args.index("--distpath") + 1])
            app = dist / "purifier-control" / "purifier-control"
            app.parent.mkdir(parents=True)
            app.write_text("fake executable", encoding="utf-8")
            return None
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
            {"app", "app/purifier-control", "bin", "bin/smctemp", "bin/LICENSE.smctemp",
             "bin/smctemp-0.7.0-source.tar.gz",
             "config.example.toml",
             "check.command", "run.command", "README.txt"},
        )
        self.assertFalse((result / "config.toml").exists())
        self.assertFalse((result / ".secrets").exists())
        self.assertNotIn(
            FAKE_TOKEN,
            "".join(path.read_text(encoding="utf-8") for path in result.rglob("*")
                    if path.is_file()),
        )

    def test_macos_build_uses_current_python_and_collects_temperature_probe(self):
        with patch("tools.build_bundle.sys.platform", "darwin"):
            result = build_bundle(self.source, self.output, "macos", platform_module.machine(),
                                  run_command=self.fake_run)
        pyinstaller_calls = [args for args in self.calls
                             if args[:3] == [sys.executable, "-m", "PyInstaller"]]
        self.assertEqual(len(pyinstaller_calls), 1)
        args = pyinstaller_calls[0]
        self.assertIn("--onedir", args)
        self.assertIn("--console", args)
        self.assertEqual(args[args.index("--name") + 1], "purifier-control")
        self.assertEqual(args[-1], str(self.source / "tools" / "packaged_entry.py"))
        for option in ("--distpath", "--workpath", "--specpath"):
            self.assertIn(option, args)
        self.assertEqual((result / "bin" / "smctemp").read_text(encoding="utf-8"),
                         "fake smctemp")
        self.assertEqual((result / "bin" / "LICENSE.smctemp").read_text(encoding="utf-8"),
                         "redistribution allowed")
        self.assertEqual((result / "bin" / "smctemp-0.7.0-source.tar.gz").read_bytes(),
                         b"fixture smctemp source archive")
        launcher = (result / "check.command").read_text(encoding="utf-8")
        self.assertIn('PATH="$BUNDLE_DIR/bin:$PATH" "$BUNDLE_DIR/app/purifier-control"', launcher)
        self.assertNotIn("export PATH", launcher)

    def test_macos_rejects_non_system_smctemp_dependency(self):
        def run(args):
            if args[0] == "otool":
                return (f"{self.smctemp}:\n\t/opt/homebrew/lib/libexample.dylib "
                        "(compatibility version 1.0.0, current version 1.0.0)\n")
            return self.fake_run(args)
        with patch("tools.build_bundle.sys.platform", "darwin"):
            with self.assertRaisesRegex(RuntimeError, "non-system dependency"):
                build_bundle(self.source, self.output, "macos", platform_module.machine(),
                             run_command=run)
        self.assertFalse(self.output.exists())

    def test_macos_rejects_missing_verified_smctemp_source(self):
        self.source_archive.unlink()
        with patch("tools.build_bundle.sys.platform", "darwin"):
            with self.assertRaisesRegex(RuntimeError, "source archive"):
                build_bundle(self.source, self.output, "macos", platform_module.machine(),
                             run_command=self.fake_run)
        self.assertFalse(self.output.exists())

    def test_macos_rejects_modified_smctemp_source(self):
        self.source_archive.write_bytes(b"different source")
        with patch("tools.build_bundle.sys.platform", "darwin"):
            with self.assertRaisesRegex(RuntimeError, "source archive"):
                build_bundle(self.source, self.output, "macos", platform_module.machine(),
                             run_command=self.fake_run)
        self.assertFalse(self.output.exists())

    def test_macos_rejects_unknown_smctemp_binary(self):
        self.smctemp.write_bytes(b"unknown binary")
        with patch("tools.build_bundle.sys.platform", "darwin"):
            with self.assertRaisesRegex(RuntimeError, "unverified smctemp binary"):
                build_bundle(self.source, self.output, "macos", platform_module.machine(),
                             run_command=self.fake_run)
        self.assertFalse(self.output.exists())

    def test_macos_rejects_missing_smctemp_license(self):
        (self.smctemp.parent.parent / "LICENSE").unlink()
        with patch("tools.build_bundle.sys.platform", "darwin"):
            with self.assertRaisesRegex(RuntimeError, "license"):
                build_bundle(self.source, self.output, "macos", platform_module.machine(),
                             run_command=self.fake_run)
        self.assertFalse(self.output.exists())

    def test_macos_rejects_altered_smctemp_license(self):
        (self.smctemp.parent.parent / "LICENSE").write_text("unrelated license",
                                                              encoding="utf-8")
        with patch("tools.build_bundle.sys.platform", "darwin"):
            with self.assertRaisesRegex(RuntimeError, "license"):
                build_bundle(self.source, self.output, "macos", platform_module.machine(),
                             run_command=self.fake_run)
        self.assertFalse(self.output.exists())

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

    def test_template_symlink_to_private_config_is_rejected(self):
        template = self.source / "config.example.toml"
        template.unlink()
        template.symlink_to(self.source / "config.toml")
        with patch("tools.build_bundle.sys.platform", "darwin"):
            with self.assertRaises(ValueError):
                build_bundle(self.source, self.output, "macos", platform_module.machine(),
                             run_command=self.fake_run)
        self.assertFalse(self.output.exists())

    def test_token_in_public_template_comment_is_rejected(self):
        template = self.source / "config.example.toml"
        template.write_text(template.read_text(encoding="utf-8") +
                            f"# {FAKE_TOKEN}\n", encoding="utf-8")
        with patch("tools.build_bundle.sys.platform", "darwin"):
            with self.assertRaises(ValueError):
                build_bundle(self.source, self.output, "macos", platform_module.machine(),
                             run_command=self.fake_run)
        self.assertFalse(self.output.exists())

    def test_unlisted_template_field_is_rejected(self):
        template = self.source / "config.example.toml"
        template.write_text(template.read_text(encoding="utf-8") +
                            'private_note = "do not publish"\n', encoding="utf-8")
        with patch("tools.build_bundle.sys.platform", "darwin"):
            with self.assertRaises(ValueError):
                build_bundle(self.source, self.output, "macos", platform_module.machine(),
                             run_command=self.fake_run)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
