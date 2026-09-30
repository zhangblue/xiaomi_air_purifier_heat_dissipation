import shutil
import sys
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from purifier_control.config import load_config


TOKEN = "0123456789abcdef0123456789abcdef"


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.directory = Path(self.temporary_directory.name)
        secrets = self.directory / ".secrets"
        secrets.mkdir()
        (secrets / "purifier-token").write_text(f"  {TOKEN}\n", encoding="utf-8")

    def config_path(self, *, platform="macos", host="192.168.250.118",
                    token_file=".secrets/purifier-token", sensor="cpu", interval=5,
                    high_temp=70, high_duration=60, recover_temp=60,
                    recover_duration=120, high_level=17, low_level=3):
        path = self.directory / "config.toml"
        path.write_text(
            f'platform = "{platform}"\n'
            f'[purifier]\nhost = "{host}"\ntoken_file = "{token_file}"\n'
            f'[system]\ntemperature_sensor = "{sensor}"\n'
            f'sample_interval_seconds = {interval}\n'
            f'[control]\nhigh_temperature_c = {high_temp}\n'
            f'high_duration_seconds = {high_duration}\n'
            f'recover_temperature_c = {recover_temp}\n'
            f'recover_duration_seconds = {recover_duration}\n'
            f'high_favorite_level = {high_level}\n'
            f'low_favorite_level = {low_level}\n',
            encoding="utf-8",
        )
        return path

    def test_macos_config_resolves_relative_token_and_all_fields(self):
        config = load_config(self.config_path(), running_platform="darwin")
        self.assertEqual(config.platform, "macos")
        self.assertEqual(config.purifier.host, "192.168.250.118")
        self.assertEqual(config.purifier.token, TOKEN)
        self.assertEqual(config.system.temperature_sensor, "cpu")
        self.assertEqual(config.system.sample_interval_seconds, 5)
        self.assertEqual(config.control.high_temperature_c, 70)
        self.assertEqual(config.control.high_duration_seconds, 60)
        self.assertEqual(config.control.recover_temperature_c, 60)
        self.assertEqual(config.control.recover_duration_seconds, 120)
        self.assertEqual(config.control.high_favorite_level, 17)
        self.assertEqual(config.control.low_favorite_level, 3)

    def test_windows_config_is_accepted_on_windows(self):
        config = load_config(self.config_path(platform="windows"), running_platform="win32")
        self.assertEqual(config.platform, "windows")

    def test_example_config_uses_confirmed_control_defaults(self):
        example_path = Path(__file__).resolve().parents[1] / "config.example.toml"
        config_path = self.directory / "config.toml"
        shutil.copyfile(example_path, config_path)
        config = load_config(config_path, running_platform="darwin")
        self.assertEqual(config.control.high_temperature_c, 60)
        self.assertEqual(config.control.high_duration_seconds, 15)
        self.assertEqual(config.control.recover_temperature_c, 55)
        self.assertEqual(config.control.recover_duration_seconds, 120)

    def test_config_is_immutable_and_repr_does_not_disclose_token(self):
        config = load_config(self.config_path(), running_platform="darwin")
        with self.assertRaises(FrozenInstanceError):
            config.platform = "windows"
        self.assertNotIn(TOKEN, repr(config))

    def test_platform_must_match_current_system(self):
        with self.assertRaisesRegex(ValueError, "platform"):
            load_config(self.config_path(platform="windows"), running_platform="darwin")

    def test_platform_auto_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "platform"):
            load_config(self.config_path(platform="auto"), running_platform="darwin")

    def test_recovery_threshold_must_be_below_high_threshold(self):
        with self.assertRaisesRegex(ValueError, "recover_temperature_c"):
            load_config(self.config_path(recover_temp=70), running_platform="darwin")

    def test_favorite_levels_must_be_ordered_and_within_range(self):
        for low, high in ((17, 3), (-1, 17), (3, 18), (3, 3)):
            with self.subTest(low=low, high=high):
                with self.assertRaisesRegex(ValueError, "favorite_level"):
                    load_config(self.config_path(low_level=low, high_level=high),
                                running_platform="darwin")

    def test_durations_and_sampling_interval_must_be_positive(self):
        cases = (
            ("interval", 0, "sample_interval_seconds"),
            ("high_duration", 0, "high_duration_seconds"),
            ("recover_duration", -1, "recover_duration_seconds"),
        )
        for field, value, expected_error in cases:
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, expected_error):
                    load_config(self.config_path(**{field: value}), running_platform="darwin")

    def test_only_cpu_sensor_is_supported(self):
        with self.assertRaisesRegex(ValueError, "temperature_sensor"):
            load_config(self.config_path(sensor="ambient"), running_platform="darwin")

    def test_token_must_be_exactly_32_hex_characters_without_leaking_it(self):
        token_path = self.directory / ".secrets" / "purifier-token"
        for secret_value in ("g" * 32, "a" * 31, "a" * 33):
            with self.subTest(secret_value=secret_value):
                token_path.write_text(secret_value, encoding="utf-8")
                with self.assertRaises(ValueError) as caught:
                    load_config(self.config_path(), running_platform="darwin")
                self.assertIn("token_file", str(caught.exception))
                self.assertNotIn(secret_value, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
