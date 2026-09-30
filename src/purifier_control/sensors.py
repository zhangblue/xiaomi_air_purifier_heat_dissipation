"""Read CPU temperature from a platform-specific local probe."""

import json
import math
import os
import subprocess
from pathlib import PureWindowsPath
from typing import Protocol


class SensorError(RuntimeError):
    """A CPU temperature could not be read safely."""


class TemperatureSource(Protocol):
    def read(self) -> float:
        """Return a finite CPU temperature in Celsius or raise SensorError."""


def _valid_temperature(value: object) -> float:
    if (isinstance(value, bool) or not isinstance(value, (float, int))
            or not math.isfinite(value) or not 0 < value <= 125):
        raise SensorError("CPU temperature is invalid")
    return float(value)


def _run_probe(command: list[str], timeout: float) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                timeout=timeout)
    except (OSError, subprocess.TimeoutExpired, subprocess.SubprocessError):
        raise SensorError("CPU temperature probe could not be run") from None
    if result.returncode != 0:
        raise SensorError("CPU temperature probe failed")
    return result.stdout


class MacOSTemperatureSource:
    def __init__(self, smctemp_path: str, *, timeout: float = 5.0):
        if not os.path.isabs(smctemp_path):
            raise ValueError("smctemp path must be absolute")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        self._path = smctemp_path
        self._timeout = timeout

    def read(self) -> float:
        output = _run_probe([self._path, "-c"], self._timeout)
        try:
            value = float(output.strip())
        except ValueError:
            raise SensorError("CPU temperature output is invalid") from None
        return _valid_temperature(value)


class WindowsTemperatureSource:
    def __init__(self, probe_path: str, *, timeout: float = 5.0):
        if not PureWindowsPath(probe_path).is_absolute():
            raise ValueError("Windows probe path must be absolute")
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("timeout must be positive and finite")
        self._path = probe_path
        self._timeout = timeout

    def read(self) -> float:
        output = _run_probe([self._path, "--json"], self._timeout)
        try:
            payload = json.loads(output, parse_constant=lambda _: None)
            value = payload["temperature_c"]
        except (ValueError, TypeError, KeyError):
            raise SensorError("CPU temperature output is invalid") from None
        return _valid_temperature(value)
