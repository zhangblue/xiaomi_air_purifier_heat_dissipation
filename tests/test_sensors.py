import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from purifier_control.sensors import (
    LinuxTemperatureSource,
    MacOSTemperatureSource,
    SensorError,
    WindowsTemperatureSource,
)


class LinuxTemperatureSourceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def package(self, name="hwmon0", driver="coretemp", label="Package id 0",
                value="61000"):
        directory = self.root / name
        directory.mkdir()
        (directory / "name").write_text(driver + "\n")
        (directory / "temp1_label").write_text(label + "\n")
        if value is not None:
            (directory / "temp1_input").write_text(value + "\n")
        return directory

    def test_reads_package_millicelsius(self):
        self.package()
        self.assertEqual(LinuxTemperatureSource(self.root).read(), 61.0)

    def test_returns_hottest_package(self):
        self.package(value="61000")
        self.package("hwmon1", label="Package id 1", value="72500")
        self.assertEqual(LinuxTemperatureSource(self.root).read(), 72.5)

    def test_ignores_other_drivers_and_non_package_labels(self):
        self.package(driver="other", value="99000")
        self.package("hwmon1", label="Package id 0 extra", value="98000")
        self.package("hwmon2", label="Core 0", value="97000")
        self.package("hwmon3", value="61000")
        self.assertEqual(LinuxTemperatureSource(self.root).read(), 61.0)

    def test_requires_a_coretemp_package(self):
        self.package(driver="other")
        with self.assertRaises(SensorError):
            LinuxTemperatureSource(self.root).read()

    def test_any_bad_package_fails_without_exposing_path_or_contents(self):
        self.package(value="61000")
        broken = self.package("hwmon1", label="Package id 1") / "temp1_input"
        for value in ("0", "126000", "private-invalid", None):
            with self.subTest(value=value):
                if value is None:
                    broken.unlink()
                else:
                    broken.write_text(value)
                with self.assertRaises(SensorError) as caught:
                    LinuxTemperatureSource(self.root).read()
                self.assertNotIn(str(self.root), str(caught.exception))
                self.assertNotIn("private-invalid", str(caught.exception))

    def test_unreadable_files_fail_safely(self):
        directory = self.package()
        original = Path.read_text
        for filename in ("name", "temp1_label", "temp1_input"):
            def read(path, *args, **kwargs):
                if path == directory / filename:
                    raise PermissionError("private-path-and-content")
                return original(path, *args, **kwargs)
            with self.subTest(filename=filename), patch.object(Path, "read_text", read):
                with self.assertRaises(SensorError) as caught:
                    LinuxTemperatureSource(self.root).read()
                self.assertNotIn("private", str(caught.exception))


class MacOSTemperatureSourceTests(unittest.TestCase):
    def setUp(self):
        self.source = MacOSTemperatureSource("/usr/local/bin/smctemp", timeout=2.5)

    def test_reads_celsius_from_smctemp(self):
        with patch("purifier_control.sensors.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 0, "64.2\n", "")) as run:
            self.assertEqual(self.source.read(), 64.2)
        run.assert_called_once_with(
            ["/usr/local/bin/smctemp", "-c"], capture_output=True,
            text=True, timeout=2.5)

    def test_rejects_failed_or_invalid_output(self):
        for code, output in ((1, "64.2\n"), (0, ""), (0, "NaN\n"),
                             (0, "-1\n"), (0, "125.1\n"), (0, "garbage\n")):
            with self.subTest(code=code, output=output):
                with patch("purifier_control.sensors.subprocess.run",
                           return_value=subprocess.CompletedProcess([], code, output, "secret")):
                    with self.assertRaises(SensorError) as caught:
                        self.source.read()
                    self.assertNotIn("secret", str(caught.exception))

    def test_rejects_process_error_without_leaking_details(self):
        for error in (FileNotFoundError("secret"),
                      subprocess.TimeoutExpired("secret", 2.5)):
            with self.subTest(error=type(error).__name__):
                with patch("purifier_control.sensors.subprocess.run", side_effect=error):
                    with self.assertRaises(SensorError) as caught:
                        self.source.read()
                    self.assertNotIn("secret", str(caught.exception))


class WindowsTemperatureSourceTests(unittest.TestCase):
    def setUp(self):
        self.source = WindowsTemperatureSource("C:\\probe\\TemperatureProbe.exe", timeout=3)

    def test_reads_json_temperature(self):
        with patch("purifier_control.sensors.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 0, '{"temperature_c":64.2}\n', "")) as run:
            self.assertEqual(self.source.read(), 64.2)
        run.assert_called_once_with(
            ["C:\\probe\\TemperatureProbe.exe", "--json"],
            capture_output=True, text=True, timeout=3)

    def test_rejects_missing_or_invalid_json_temperature(self):
        for output in ('{}', 'not json', '{"temperature_c":"64.2"}',
                       '{"temperature_c":null}', '{"temperature_c":126}',
                       '{"temperature_c":-1}', '{"temperature_c":0}',
                       '{"temperature_c":NaN}'):
            with self.subTest(output=output):
                with patch("purifier_control.sensors.subprocess.run",
                           return_value=subprocess.CompletedProcess([], 0, output, "")):
                    with self.assertRaises(SensorError):
                        self.source.read()

    def test_rejects_failed_probe(self):
        with patch("purifier_control.sensors.subprocess.run",
                   return_value=subprocess.CompletedProcess([], 2, "", "secret")):
            with self.assertRaises(SensorError) as caught:
                self.source.read()
            self.assertNotIn("secret", str(caught.exception))


class SourceConfigurationTests(unittest.TestCase):
    def test_rejects_relative_paths_and_invalid_timeout(self):
        for source_type in (MacOSTemperatureSource, WindowsTemperatureSource):
            with self.subTest(source_type=source_type.__name__):
                with self.assertRaises(ValueError):
                    source_type("relative/tool")
                with self.assertRaises(ValueError):
                    source_type("/absolute/tool", timeout=0)

    def test_windows_probe_rejects_drive_relative_or_root_relative_path(self):
        for path in (r"C:probe\TemperatureProbe.exe",
                     r"\probe\TemperatureProbe.exe"):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    WindowsTemperatureSource(path)


if __name__ == "__main__":
    unittest.main()
