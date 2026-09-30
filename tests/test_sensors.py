import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from purifier_control.sensors import (
    MacOSTemperatureSource,
    SensorError,
    WindowsTemperatureSource,
)


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
