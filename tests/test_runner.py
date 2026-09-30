import io
import logging
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from miio.integrations.airpurifier.zhimi.airpurifier import OperationMode
from purifier_control.config import AppConfig, ControlConfig, PurifierConfig, SystemConfig
from purifier_control.policy import TemperaturePolicy
from purifier_control.purifier import MiioPurifier, PurifierError, PurifierLevelRejected
from purifier_control.sensors import SensorError
from purifier_control.runner import Runner
from purifier_control.cli import main
from tests.test_purifier import FakeDevice


CONTROL = ControlConfig(60.0, 15.0, 55.0, 120.0, 17, 3)
CONFIG = AppConfig("macos", PurifierConfig("192.0.2.10", "secret-token"),
                   SystemConfig("cpu", 5.0), CONTROL)


class FakeSensor:
    def __init__(self, readings):
        self.readings = iter(readings)
        self.read_count = 0

    def read(self):
        self.read_count += 1
        value = next(self.readings)
        if isinstance(value, Exception):
            raise value
        return value


class FakePurifier:
    def __init__(self):
        self.calls = []
        self.is_on = False
        self.mode = OperationMode.Auto
        self.level = 1
        self.fail_reads = 0
        self.fail_writes = 0
        self.reject_level = None
        self.reject_start_level = None
        self.fail_info = 0

    def verify_model(self):
        self.calls.append("info")
        if self.fail_info:
            self.fail_info -= 1
            raise PurifierError("secret-token")
        return SimpleNamespace(model="zhimi.airpurifier.v6")

    def read_info(self):
        self.calls.append("info")
        return SimpleNamespace(model="zhimi.airpurifier.v6")

    def read_status(self):
        self.calls.append("status")
        if self.fail_reads:
            self.fail_reads -= 1
            raise PurifierError("unavailable")
        return SimpleNamespace(is_on=self.is_on, mode=self.mode,
                               favorite_level=self.level)

    def start(self, level):
        self.calls.append(("start", level))
        if level == self.reject_start_level:
            raise PurifierLevelRejected("secret-token")
        if self.fail_writes:
            self.fail_writes -= 1
            raise PurifierError("unavailable")
        self.is_on = True
        self.mode = OperationMode.Favorite
        self.level = level
        return self.read_status()

    def set_level(self, level):
        self.calls.append(("level", level))
        if level == self.reject_level:
            raise PurifierLevelRejected("secret-token")
        if self.fail_writes:
            self.fail_writes -= 1
            raise PurifierError("unavailable")
        self.level = level
        return self.read_status()


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.waits = []
        self.interrupt_at = None

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.waits.append(seconds)
        self.now += seconds
        if self.interrupt_at is not None and self.now >= self.interrupt_at:
            raise KeyboardInterrupt


def runner(sensor, purifier, clock=None):
    clock = clock or FakeClock()
    logger = logging.getLogger("test.purifier.runner")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    return Runner(sensor, purifier, TemperaturePolicy(CONTROL),
                  sample_interval_seconds=5.0, clock=clock.monotonic,
                  wait=clock.sleep, logger=logger)


class RunnerTests(unittest.TestCase):
    def test_start_low_then_switches_once_after_each_duration(self):
        sensor = FakeSensor([61.0] * 5 + [54.0] * 26)
        purifier = FakePurifier()
        subject = runner(sensor, purifier)

        for now in range(0, 155, 5):
            subject.tick(float(now))

        self.assertEqual(sensor.read_count, 31)
        self.assertEqual([call for call in purifier.calls if isinstance(call, tuple)],
                         [("start", 3), ("level", 17), ("level", 3)])
        self.assertEqual(subject.desired_level, 3)

    def test_sensor_error_keeps_level_and_interrupts_duration(self):
        sensor = FakeSensor([61.0, 61.0, SensorError("secret-token"), 61.0,
                             61.0, 61.0, 61.0])
        purifier = FakePurifier()
        subject = runner(sensor, purifier)

        for now in range(0, 35, 5):
            subject.tick(float(now))

        self.assertEqual([call for call in purifier.calls if isinstance(call, tuple)],
                         [("start", 3), ("level", 17)])
        self.assertEqual(purifier.level, 17)

    def test_failed_read_uses_bounded_backoff_then_reconciles_actual_level(self):
        sensor = FakeSensor([61.0] * 20)
        purifier = FakePurifier()
        purifier.fail_reads = 4
        subject = runner(sensor, purifier)

        for now in range(0, 80, 5):
            subject.tick(float(now))

        self.assertEqual([call for call in purifier.calls if call == "status"],
                         ["status"] * 7)
        self.assertEqual([call for call in purifier.calls if isinstance(call, tuple)],
                         [("start", 3), ("level", 17)])
        self.assertEqual(subject.desired_level, 17)

    def test_failed_write_preserves_desired_level_until_readback(self):
        sensor = FakeSensor([61.0] * 8)
        purifier = FakePurifier()
        subject = runner(sensor, purifier)
        for now in (0.0, 5.0, 10.0):
            subject.tick(now)
        purifier.fail_writes = 1
        subject.tick(15.0)

        self.assertEqual(subject.desired_level, 17)
        self.assertEqual(purifier.level, 3)
        subject.tick(20.0)
        self.assertEqual(purifier.level, 17)
        subject.tick(25.0)
        self.assertEqual(purifier.level, 17)
        self.assertEqual([call for call in purifier.calls if call == ("level", 17)],
                         [("level", 17), ("level", 17)])

    def test_recovery_reads_state_before_rewriting_changed_actual_level(self):
        sensor = FakeSensor([61.0] * 8)
        purifier = FakePurifier()
        subject = runner(sensor, purifier)
        for now in (0.0, 5.0, 10.0, 15.0):
            if now == 15.0:
                purifier.fail_reads = 1
            subject.tick(now)
        purifier.level = 3
        subject.tick(20.0)
        subject.tick(25.0)

        self.assertEqual(purifier.calls[-3:], ["status", ("level", 17), "status"])
        self.assertEqual(purifier.level, 17)

    def test_offline_start_recovers_then_applies_low_before_pending_high(self):
        sensor = FakeSensor([61.0] * 15)
        purifier = FakePurifier()
        purifier.fail_info = 4
        subject = runner(sensor, purifier)

        for now in range(0, 65, 5):
            subject.tick(float(now))
        self.assertFalse(any(isinstance(call, tuple) for call in purifier.calls))
        subject.tick(65.0)
        subject.tick(70.0)

        self.assertEqual(subject.desired_level, 17)
        self.assertEqual([call for call in purifier.calls if isinstance(call, tuple)],
                         [("start", 3), ("level", 17)])
        self.assertEqual(purifier.level, 17)

    def test_delayed_readback_does_not_permanently_block_target(self):
        sensor = FakeSensor([61.0] * 6)
        device = FakeDevice()
        purifier = MiioPurifier(device, expected_model="zhimi.airpurifier.v6")
        subject = runner(sensor, purifier)
        for now in (0.0, 5.0, 10.0):
            subject.tick(now)
        device.reported_level = 3
        subject.tick(15.0)
        device.reported_level = None
        subject.tick(20.0)

        self.assertEqual(device.favorite_level, 17)
        self.assertEqual(device.calls.count("status"), 4)
        self.assertEqual([call for call in device.calls if call == ("level", 17)],
                         [("level", 17)])

    def test_many_network_failures_keep_retry_delay_finite(self):
        sensor = FakeSensor([57.0] * 1050)
        purifier = FakePurifier()
        purifier.fail_reads = 1030
        subject = runner(sensor, purifier)

        for now in range(0, 1050 * 30, 30):
            subject.tick(float(now))

        self.assertEqual(purifier.level, 3)

    def test_rejected_level_is_not_retried_while_target_remains_same(self):
        sensor = FakeSensor([61.0] * 8)
        purifier = FakePurifier()
        purifier.reject_level = 17
        subject = runner(sensor, purifier)

        for now in range(0, 40, 5):
            subject.tick(float(now))

        self.assertEqual(subject.desired_level, 17)
        self.assertEqual(purifier.level, 3)
        self.assertEqual([call for call in purifier.calls if call == ("level", 17)],
                         [("level", 17)])

    def test_rejected_startup_low_is_reported_as_low_and_not_retried(self):
        sensor = FakeSensor([61.0] * 10)
        purifier = FakePurifier()
        purifier.fail_info = 2
        purifier.reject_start_level = 3
        subject = runner(sensor, purifier)
        events = io.StringIO()
        handler = logging.StreamHandler(events)
        subject.log.addHandler(handler)
        try:
            for now in range(0, 50, 5):
                subject.tick(float(now))
        finally:
            subject.log.removeHandler(handler)

        self.assertEqual(subject.desired_level, 17)
        self.assertEqual([call for call in purifier.calls if isinstance(call, tuple)],
                         [("start", 3)])
        self.assertIn("rejected Favorite level 3", events.getvalue())
        self.assertNotIn("rejected Favorite level 17", events.getvalue())
        self.assertNotIn("secret-token", events.getvalue())

    def test_run_samples_at_configured_interval_and_interrupt_does_not_power_off(self):
        clock = FakeClock()
        clock.interrupt_at = 15.0
        sensor = FakeSensor([61.0] * 4)
        purifier = FakePurifier()

        runner(sensor, purifier, clock).run()

        self.assertEqual(sensor.read_count, 3)
        self.assertEqual(clock.waits, [5.0, 5.0, 5.0])
        self.assertEqual([call for call in purifier.calls if isinstance(call, tuple)],
                         [("start", 3)])
        self.assertFalse(any(call == "off" for call in purifier.calls))


class CliTests(unittest.TestCase):
    def test_check_reports_reachable_wrong_model_accurately(self):
        sensor = FakeSensor([42.5])
        device = FakeDevice(model="zhimi.airpurifier.v7")
        purifier = MiioPurifier(device, expected_model="zhimi.airpurifier.v6",
                                verify=False)
        output = io.StringIO()
        with (patch("purifier_control.cli.load_config", return_value=CONFIG),
              patch("purifier_control.cli.make_sensor", return_value=sensor),
              patch("purifier_control.cli.make_purifier", return_value=purifier),
              patch("sys.stdout", output)):
            code = main(["--config", "unused.toml", "check"])

        self.assertEqual(code, 1)
        self.assertIn("Internal model: zhimi.airpurifier.v7", output.getvalue())
        self.assertIn("Connection: connected", output.getvalue())
        self.assertIn("Model verification: mismatch", output.getvalue())
        self.assertEqual(device.calls, ["info"])

    def test_run_constructs_adapter_without_initial_network_read(self):
        sensor = FakeSensor([42.5])
        purifier = FakePurifier()
        with (patch("purifier_control.cli.load_config", return_value=CONFIG),
              patch("purifier_control.cli.make_sensor", return_value=sensor),
              patch("purifier_control.cli.MiioPurifier.from_host", return_value=purifier)
              as factory,
              patch("purifier_control.cli.Runner.run")):
            code = main(["--config", "unused.toml", "run"])

        self.assertEqual(code, 0)
        factory.assert_called_once_with("192.0.2.10", "secret-token",
                                        expected_model="zhimi.airpurifier.v6",
                                        verify=False)

    def test_check_reads_only_and_never_prints_token(self):
        sensor = FakeSensor([42.5])
        purifier = FakePurifier()
        output = io.StringIO()
        with (patch("purifier_control.cli.load_config", return_value=CONFIG),
              patch("purifier_control.cli.make_sensor", return_value=sensor),
              patch("purifier_control.cli.make_purifier", return_value=purifier),
              patch("sys.stdout", output)):
            code = main(["--config", "unused.toml", "check"])

        self.assertEqual(code, 0)
        self.assertEqual(purifier.calls, ["info", "status"])
        self.assertIn("42.5", output.getvalue())
        self.assertIn("192.0.2.10", output.getvalue())
        self.assertIn("zhimi.airpurifier.v6", output.getvalue())
        self.assertIn("connected", output.getvalue().lower())
        self.assertNotIn("secret-token", output.getvalue())

    def test_check_reports_disconnected_without_writing_or_exposing_error(self):
        sensor = FakeSensor([42.5])
        purifier = FakePurifier()
        purifier.fail_reads = 1
        output = io.StringIO()
        with (patch("purifier_control.cli.load_config", return_value=CONFIG),
              patch("purifier_control.cli.make_sensor", return_value=sensor),
              patch("purifier_control.cli.make_purifier", return_value=purifier),
              patch("sys.stdout", output)):
            code = main(["--config", "unused.toml", "check"])

        self.assertEqual(code, 1)
        self.assertEqual(purifier.calls, ["info", "status"])
        self.assertIn("Connection: disconnected", output.getvalue())
        self.assertEqual(output.getvalue().count("Internal model:"), 1)
        self.assertIn("42.5", output.getvalue())
        self.assertNotIn("secret-token", output.getvalue())

    def test_check_keeps_local_fields_when_device_info_is_unavailable(self):
        sensor = FakeSensor([42.5])
        output = io.StringIO()
        with (patch("purifier_control.cli.load_config", return_value=CONFIG),
              patch("purifier_control.cli.make_sensor", return_value=sensor),
              patch("purifier_control.cli.make_purifier",
                    side_effect=PurifierError("secret-token")),
              patch("sys.stdout", output)):
            code = main(["--config", "unused.toml", "check"])

        self.assertEqual(code, 1)
        self.assertIn("Platform: macos", output.getvalue())
        self.assertIn("42.5", output.getvalue())
        self.assertIn("192.0.2.10", output.getvalue())
        self.assertIn("Connection: disconnected", output.getvalue())
        self.assertNotIn("secret-token", output.getvalue())


if __name__ == "__main__":
    unittest.main()
