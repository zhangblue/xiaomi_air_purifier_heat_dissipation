import math
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from purifier_control.config import ControlConfig
from purifier_control.policy import TemperaturePolicy


class TemperaturePolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = TemperaturePolicy(ControlConfig(60.0, 15.0, 55.0, 120.0, 17, 3))

    def test_starts_low_and_requires_strict_high_threshold_for_full_duration(self):
        self.assertEqual(self.policy.current_level, 3)
        self.assertIsNone(self.policy.observe(60.0, 0.0))
        self.assertIsNone(self.policy.observe(60.1, 1.0))
        self.assertIsNone(self.policy.observe(60.1, 15.9))
        self.assertEqual(self.policy.observe(60.1, 16.0), 17)
        self.assertIsNone(self.policy.observe(60.1, 17.0))

    def test_high_candidate_resets_at_threshold(self):
        self.assertIsNone(self.policy.observe(60.1, 0.0))
        self.assertIsNone(self.policy.observe(60.0, 14.0))
        self.assertIsNone(self.policy.observe(60.1, 15.0))
        self.assertIsNone(self.policy.observe(60.1, 29.9))
        self.assertEqual(self.policy.observe(60.1, 30.0), 17)

    def test_recovery_requires_strict_low_threshold_for_full_duration(self):
        self.assertIsNone(self.policy.observe(60.1, 0.0))
        self.assertEqual(self.policy.observe(60.1, 15.0), 17)
        self.assertIsNone(self.policy.observe(55.0, 16.0))
        self.assertIsNone(self.policy.observe(54.9, 20.0))
        self.assertIsNone(self.policy.observe(54.9, 139.9))
        self.assertEqual(self.policy.observe(54.9, 140.0), 3)
        self.assertIsNone(self.policy.observe(54.9, 141.0))

    def test_recovery_candidate_resets_at_threshold(self):
        self.policy.observe(60.1, 0.0)
        self.policy.observe(60.1, 15.0)
        self.assertIsNone(self.policy.observe(54.9, 20.0))
        self.assertIsNone(self.policy.observe(55.0, 100.0))
        self.assertIsNone(self.policy.observe(54.9, 101.0))
        self.assertIsNone(self.policy.observe(54.9, 220.9))
        self.assertEqual(self.policy.observe(54.9, 221.0), 3)

    def test_invalid_readings_interrupt_high_candidate(self):
        for invalid in (None, math.nan, math.inf, -math.inf):
            with self.subTest(invalid=invalid):
                policy = TemperaturePolicy(ControlConfig(60.0, 15.0, 55.0, 120.0, 17, 3))
                self.assertIsNone(policy.observe(60.1, 0.0))
                self.assertIsNone(policy.observe(invalid, 14.0))
                self.assertIsNone(policy.observe(60.1, 15.0))
                self.assertIsNone(policy.observe(60.1, 29.9))
                self.assertEqual(policy.observe(60.1, 30.0), 17)

    def test_invalid_readings_interrupt_recovery_candidate(self):
        for invalid in (None, math.nan, math.inf, -math.inf):
            with self.subTest(invalid=invalid):
                policy = TemperaturePolicy(ControlConfig(60.0, 15.0, 55.0, 120.0, 17, 3))
                policy.observe(60.1, 0.0)
                policy.observe(60.1, 15.0)
                self.assertIsNone(policy.observe(54.9, 20.0))
                self.assertIsNone(policy.observe(invalid, 139.0))
                self.assertIsNone(policy.observe(54.9, 140.0))
                self.assertIsNone(policy.observe(54.9, 259.9))
                self.assertEqual(policy.observe(54.9, 260.0), 3)

    def test_middle_band_preserves_both_levels(self):
        self.assertIsNone(self.policy.observe(57.0, 0.0))
        self.assertEqual(self.policy.current_level, 3)
        self.policy.observe(60.1, 1.0)
        self.policy.observe(60.1, 16.0)
        self.assertIsNone(self.policy.observe(57.0, 17.0))
        self.assertEqual(self.policy.current_level, 17)

    def test_uses_configured_levels_thresholds_and_durations(self):
        policy = TemperaturePolicy(ControlConfig(72.0, 4.0, 64.0, 8.0, 12, 2))
        self.assertEqual(policy.current_level, 2)
        self.assertIsNone(policy.observe(72.0, 0.0))
        self.assertIsNone(policy.observe(72.1, 1.0))
        self.assertEqual(policy.observe(72.1, 5.0), 12)
        self.assertIsNone(policy.observe(64.0, 6.0))
        self.assertIsNone(policy.observe(63.9, 7.0))
        self.assertEqual(policy.observe(63.9, 15.0), 2)

    def test_rejects_backwards_timestamps_without_changing_candidate(self):
        self.assertIsNone(self.policy.observe(60.1, 10.0))
        with self.assertRaises(ValueError):
            self.policy.observe(60.1, 9.0)
        self.assertIsNone(self.policy.observe(60.1, 24.9))
        self.assertEqual(self.policy.observe(60.1, 25.0), 17)


if __name__ == "__main__":
    unittest.main()
