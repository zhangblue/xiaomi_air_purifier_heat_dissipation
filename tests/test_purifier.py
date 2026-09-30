import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from miio.integrations.airpurifier.zhimi.airpurifier import OperationMode
from purifier_control.purifier import (MiioPurifier, PurifierError,
                                      PurifierLevelRejected, PurifierModelMismatch)


MODEL = "zhimi.airpurifier.v6"
TOKEN = "0123456789abcdef0123456789abcdef"


class FakeDevice:
    def __init__(self, *, model=MODEL, fail_on=None):
        self.model = model
        self.fail_on = fail_on
        self.calls = []
        self.is_on = False
        self.mode = OperationMode.Auto
        self.favorite_level = 1
        self.reported_level = None
        self.reported_mode = None
        self.reported_power = None

    def _record(self, call):
        self.calls.append(call)
        if call == self.fail_on:
            raise RuntimeError(f"device failure with secret {TOKEN}")

    def info(self):
        self._record("info")
        return SimpleNamespace(model=self.model)

    def on(self):
        self._record("on")
        self.is_on = True

    def set_favorite_level(self, level):
        self._record(("level", level))
        self.favorite_level = level

    def set_mode(self, mode):
        self._record(("mode", mode.value))
        self.mode = mode

    def status(self):
        self._record("status")
        return SimpleNamespace(
            is_on=self.is_on if self.reported_power is None else self.reported_power,
            mode=self.mode if self.reported_mode is None else self.reported_mode,
            favorite_level=(self.favorite_level if self.reported_level is None
                            else self.reported_level),
        )


class MiioPurifierTests(unittest.TestCase):
    def test_public_reads_return_device_data_without_control_commands(self):
        device = FakeDevice()
        adapter = MiioPurifier(device, expected_model=MODEL)
        device.calls.clear()

        self.assertEqual(adapter.read_info().model, MODEL)
        self.assertFalse(adapter.read_status().is_on)
        self.assertEqual(device.calls, ["info", "status"])

    def test_public_read_failure_is_sanitized(self):
        device = FakeDevice()
        adapter = MiioPurifier(device, expected_model=MODEL)
        device.fail_on = "status"

        with self.assertRaises(PurifierError) as caught:
            adapter.read_status()
        self.assertNotIn(TOKEN, str(caught.exception))

    def test_wrong_model_rejects_without_writing_commands(self):
        device = FakeDevice(model="zhimi.airpurifier.v7")
        with self.assertRaisesRegex(PurifierModelMismatch, "model") as caught:
            MiioPurifier(device, expected_model=MODEL)
        self.assertEqual(caught.exception.reported_model, "zhimi.airpurifier.v7")
        self.assertEqual(device.calls, ["info"])

    def test_start_writes_in_order_then_confirms_status(self):
        device = FakeDevice()
        adapter = MiioPurifier(device, expected_model=MODEL)

        result = adapter.start(3)

        self.assertEqual(device.calls, ["info", "on", ("level", 3),
                                        ("mode", "favorite"), "status"])
        self.assertTrue(result.is_on)
        self.assertEqual(result.mode, OperationMode.Favorite)
        self.assertEqual(result.favorite_level, 3)

    def test_later_level_change_only_writes_level_and_reads_back(self):
        device = FakeDevice()
        adapter = MiioPurifier(device, expected_model=MODEL)
        adapter.start(3)
        device.calls.clear()

        result = adapter.set_level(17)

        self.assertEqual(device.calls, [("level", 17), "status"])
        self.assertEqual(result.favorite_level, 17)

    def test_readback_rejects_wrong_power_mode_or_level(self):
        for field, value in (("reported_power", False),
                             ("reported_mode", OperationMode.Auto),
                             ("reported_level", 2)):
            with self.subTest(field=field):
                device = FakeDevice()
                setattr(device, field, value)
                adapter = MiioPurifier(device, expected_model=MODEL)
                with self.assertRaises(PurifierError):
                    adapter.start(3)
                self.assertEqual(device.calls[-1], "status")

    def test_level_change_rejects_wrong_readback(self):
        device = FakeDevice()
        adapter = MiioPurifier(device, expected_model=MODEL)
        adapter.start(3)
        device.reported_level = 3
        device.calls.clear()

        with self.assertRaises(PurifierError) as caught:
            adapter.set_level(17)
        self.assertNotIsInstance(caught.exception, PurifierLevelRejected)
        self.assertEqual(device.calls, [("level", 17), "status"])

    def test_host_factory_can_defer_model_read_until_device_recovers(self):
        device = FakeDevice(fail_on="info")
        with patch("miio.AirPurifier", return_value=device):
            adapter = MiioPurifier.from_host("192.0.2.10", TOKEN,
                                             expected_model=MODEL, verify=False)
        self.assertEqual(device.calls, [])
        with self.assertRaises(PurifierError):
            adapter.verify_model()
        device.fail_on = None
        self.assertEqual(adapter.verify_model().model, MODEL)

    def test_explicit_false_level_response_is_rejection(self):
        device = FakeDevice()
        adapter = MiioPurifier(device, expected_model=MODEL)
        device.set_favorite_level = lambda level: False

        with self.assertRaises(PurifierLevelRejected):
            adapter.set_level(17)

    def test_library_failures_never_claim_success_or_reveal_token(self):
        for failure in ("info", "on", ("level", 3),
                        ("mode", "favorite"), "status"):
            with self.subTest(failure=failure):
                device = FakeDevice(fail_on=failure)
                if failure == "info":
                    action = lambda: MiioPurifier(device, expected_model=MODEL)
                else:
                    adapter = MiioPurifier(device, expected_model=MODEL)
                    action = lambda: adapter.start(3)
                with self.assertRaises(PurifierError) as caught:
                    action()
                self.assertNotIn(TOKEN, str(caught.exception))
                self.assertNotIn("status", device.calls[:-1])

    def test_host_factory_uses_pinned_library_constructor(self):
        device = FakeDevice()
        with patch("miio.AirPurifier", return_value=device) as constructor:
            adapter = MiioPurifier.from_host("192.0.2.10", TOKEN,
                                             expected_model=MODEL)
        constructor.assert_called_once_with("192.0.2.10", TOKEN)
        self.assertEqual(adapter.start(3).favorite_level, 3)


if __name__ == "__main__":
    unittest.main()
