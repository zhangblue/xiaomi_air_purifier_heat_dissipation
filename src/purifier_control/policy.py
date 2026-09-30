"""Decide favorite-level changes from a sequence of temperature samples."""

from __future__ import annotations

import math

from purifier_control.config import ControlConfig


class TemperaturePolicy:
    def __init__(self, config: ControlConfig) -> None:
        self.config = config
        self.current_level = config.low_favorite_level
        self.candidate_since: float | None = None
        self.candidate_direction: str | None = None
        self._last_observed_at: float | None = None

    def observe(self, temperature_c: float | None, now: float) -> int | None:
        """Return a new target level only after a continuous qualifying interval."""
        if not math.isfinite(now):
            raise ValueError("observation timestamp must be finite")
        if self._last_observed_at is not None and now < self._last_observed_at:
            raise ValueError("observation timestamp must not move backwards")
        self._last_observed_at = now

        direction: str | None = None
        if temperature_c is not None and math.isfinite(temperature_c):
            if (self.current_level == self.config.low_favorite_level
                    and temperature_c > self.config.high_temperature_c):
                direction = "high"
            elif (self.current_level == self.config.high_favorite_level
                  and temperature_c < self.config.recover_temperature_c):
                direction = "low"

        if direction is None:
            self.candidate_since = None
            self.candidate_direction = None
            return None

        if self.candidate_direction != direction:
            self.candidate_since = now
            self.candidate_direction = direction
            return None

        duration = (self.config.high_duration_seconds if direction == "high"
                    else self.config.recover_duration_seconds)
        if now - self.candidate_since < duration:
            return None

        self.current_level = (self.config.high_favorite_level if direction == "high"
                              else self.config.low_favorite_level)
        self.candidate_since = None
        self.candidate_direction = None
        return self.current_level
