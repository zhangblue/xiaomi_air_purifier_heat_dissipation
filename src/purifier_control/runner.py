"""Sample temperature and reconcile a desired Favorite level with the device."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from miio.integrations.airpurifier.zhimi.airpurifier import OperationMode

from purifier_control.policy import TemperaturePolicy
from purifier_control.purifier import (PurifierError, PurifierLevelRejected,
                                      PurifierModelMismatch)
from purifier_control.sensors import SensorError, TemperatureSource


class Runner:
    def __init__(self, sensor: TemperatureSource, purifier,
                 policy: TemperaturePolicy, *, sample_interval_seconds: float,
                 clock: Callable[[], float] = time.monotonic,
                 wait: Callable[[float], None] = time.sleep,
                 logger: logging.Logger | None = None) -> None:
        self.sensor = sensor
        self.purifier = purifier
        self.policy = policy
        self.sample_interval_seconds = sample_interval_seconds
        self.clock = clock
        self.wait = wait
        self.log = logger or logging.getLogger(__name__)
        self.desired_level = policy.current_level
        self._started = False
        self._model_verified = False
        self._connected = True
        self._next_device_attempt = 0.0
        self._failures = 0
        self._sensor_failed = False
        self._blocked_level: int | None = None
        self._last_sample_at: float | None = None
        self._needs_reconcile = False

    def tick(self, now: float) -> None:
        """Take one sample and attempt any due device reconciliation."""
        if (self._last_sample_at is not None
                and now - self._last_sample_at > 2 * self.sample_interval_seconds):
            self.policy.observe(None, now)
            if self._started:
                self._needs_reconcile = True
        self._last_sample_at = now
        try:
            temperature = self.sensor.read()
        except SensorError:
            temperature = None
            if not self._sensor_failed:
                self.log.warning("CPU temperature reading failed")
            self._sensor_failed = True
        else:
            if self._sensor_failed:
                self.log.info("CPU temperature reading recovered")
            self._sensor_failed = False

        new_level = self.policy.observe(temperature, now)
        if new_level is not None:
            self.desired_level = new_level
            if self._started and self.desired_level != self._blocked_level:
                self._blocked_level = None

        if self._blocked_level is not None and (
                not self._started or self.desired_level == self._blocked_level
                ) and not self._needs_reconcile:
            return

        if now < self._next_device_attempt:
            return

        attempted_level = self.desired_level
        try:
            if not self._model_verified:
                self.purifier.verify_model()
                self._model_verified = True
            if not self._started:
                self.purifier.read_status()
                low_level = self.policy.config.low_favorite_level
                attempted_level = low_level
                self.purifier.start(low_level)
                self._started = True
                self.log.info("Purifier set to Favorite level %d", low_level)
                if self.desired_level != low_level:
                    attempted_level = self.desired_level
                    self.purifier.set_level(self.desired_level)
                    self.log.info("Purifier set to Favorite level %d", self.desired_level)
            elif not self._connected or self._needs_reconcile:
                status = self.purifier.read_status()
                if self.desired_level != self._blocked_level:
                    self._reconcile(status)
            elif new_level is not None:
                self.purifier.set_level(self.desired_level)
                self.log.info("Purifier set to Favorite level %d", self.desired_level)
        except PurifierModelMismatch:
            raise
        except PurifierLevelRejected:
            self._blocked_level = attempted_level
            self._needs_reconcile = False
            self.log.error("Purifier rejected Favorite level %d; verify configured level",
                           attempted_level)
            return
        except PurifierError:
            if self._connected:
                self.log.warning("Purifier connection or readback failed")
            self._connected = False
            self._next_device_attempt = now + min(30.0, 5.0 * 2 ** self._failures)
            self._failures = min(self._failures + 1, 3)
            return

        if not self._connected:
            self.log.info("Purifier connection recovered")
        self._connected = True
        self._needs_reconcile = False
        self._failures = 0
        self._next_device_attempt = now

    def _reconcile(self, status) -> None:
        if not status.is_on or status.mode != OperationMode.Favorite:
            self.purifier.start(self.desired_level)
            self.log.info("Purifier set to Favorite level %d", self.desired_level)
        elif status.favorite_level != self.desired_level:
            self.purifier.set_level(self.desired_level)
            self.log.info("Purifier set to Favorite level %d", self.desired_level)

    def run(self) -> None:
        """Run until interrupted; stopping leaves purifier power unchanged."""
        next_sample = self.clock()
        try:
            while True:
                now = self.clock()
                if now < next_sample:
                    self.wait(next_sample - now)
                    continue
                self.tick(now)
                next_sample += self.sample_interval_seconds
                if next_sample <= now:
                    next_sample = now + self.sample_interval_seconds
        except KeyboardInterrupt:
            self.log.info("Stopped; purifier left in its current state")
