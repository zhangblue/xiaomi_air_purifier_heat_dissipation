"""Read and validate local purifier control configuration."""

from __future__ import annotations

import math
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PurifierConfig:
    host: str
    token: str = field(repr=False)


@dataclass(frozen=True)
class SystemConfig:
    temperature_sensor: str
    sample_interval_seconds: float


@dataclass(frozen=True)
class ControlConfig:
    high_temperature_c: float
    high_duration_seconds: float
    recover_temperature_c: float
    recover_duration_seconds: float
    high_favorite_level: int
    low_favorite_level: int


@dataclass(frozen=True)
class AppConfig:
    platform: str
    purifier: PurifierConfig
    system: SystemConfig
    control: ControlConfig


def _table(data: dict[str, Any], name: str, path: Path) -> dict[str, Any]:
    value = data.get(name)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: [{name}] must be a table")
    return value


def _string(data: dict[str, Any], name: str, path: Path) -> str:
    value = data.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: {name} must be a non-empty string")
    return value


def _number(data: dict[str, Any], name: str, path: Path) -> float:
    value = data.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{path}: {name} must be a finite number")
    return float(value)


def _level(data: dict[str, Any], name: str, path: Path) -> int:
    value = data.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path}: {name} must be an integer")
    return value


def load_config(path: Path, running_platform: str | None = None) -> AppConfig:
    """Load TOML configuration and the referenced token from disk."""
    path = Path(path)
    try:
        with path.open("rb") as source:
            data = tomllib.load(source)
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"{path}: invalid TOML configuration") from None

    platform = _string(data, "platform", path)
    actual_platform = running_platform if running_platform is not None else sys.platform
    actual_platform = {"darwin": "macos", "win32": "windows"}.get(actual_platform, actual_platform)
    if platform not in ("macos", "windows") or platform != actual_platform:
        raise ValueError(f"{path}: platform must be macos or windows and match the running system")

    purifier = _table(data, "purifier", path)
    host = _string(purifier, "host", path)
    token_file = _string(purifier, "token_file", path)
    token_path = path.parent / token_file
    try:
        token = token_path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"{path}: token_file {token_path} cannot be read") from None
    if re.fullmatch(r"[0-9a-fA-F]{32}", token) is None:
        raise ValueError(f"{path}: token_file {token_path} must contain 32 hexadecimal characters")

    system = _table(data, "system", path)
    temperature_sensor = _string(system, "temperature_sensor", path)
    if temperature_sensor != "cpu":
        raise ValueError(f"{path}: temperature_sensor must be cpu")
    sample_interval_seconds = _number(system, "sample_interval_seconds", path)
    if sample_interval_seconds <= 0:
        raise ValueError(f"{path}: sample_interval_seconds must be positive")

    control = _table(data, "control", path)
    high_temperature_c = _number(control, "high_temperature_c", path)
    high_duration_seconds = _number(control, "high_duration_seconds", path)
    recover_temperature_c = _number(control, "recover_temperature_c", path)
    recover_duration_seconds = _number(control, "recover_duration_seconds", path)
    high_favorite_level = _level(control, "high_favorite_level", path)
    low_favorite_level = _level(control, "low_favorite_level", path)
    if recover_temperature_c >= high_temperature_c:
        raise ValueError(f"{path}: recover_temperature_c must be below high_temperature_c")
    if high_duration_seconds <= 0:
        raise ValueError(f"{path}: high_duration_seconds must be positive")
    if recover_duration_seconds <= 0:
        raise ValueError(f"{path}: recover_duration_seconds must be positive")
    if not 0 <= low_favorite_level < high_favorite_level <= 17:
        raise ValueError(f"{path}: favorite_level values must satisfy 0 <= low < high <= 17")

    return AppConfig(
        platform=platform,
        purifier=PurifierConfig(host=host, token=token),
        system=SystemConfig(temperature_sensor, sample_interval_seconds),
        control=ControlConfig(
            high_temperature_c,
            high_duration_seconds,
            recover_temperature_c,
            recover_duration_seconds,
            high_favorite_level,
            low_favorite_level,
        ),
    )
