"""Manual command line entry point for checking and running the controller."""

from __future__ import annotations

import argparse
import logging
import shutil
from pathlib import Path

from purifier_control.config import AppConfig, load_config
from purifier_control.policy import TemperaturePolicy
from purifier_control.purifier import MiioPurifier, PurifierError, PurifierModelMismatch
from purifier_control.runner import Runner
from purifier_control.sensors import (MacOSTemperatureSource, SensorError,
                                      WindowsTemperatureSource)


EXPECTED_MODEL = "zhimi.airpurifier.v6"


def make_sensor(config: AppConfig):
    program = "smctemp" if config.platform == "macos" else "TemperatureProbe.exe"
    path = shutil.which(program)
    if path is None:
        raise ValueError(f"CPU temperature program {program} was not found on PATH")
    if config.platform == "macos":
        return MacOSTemperatureSource(path)
    return WindowsTemperatureSource(path)


def make_purifier(config: AppConfig, *, verify: bool = True):
    return MiioPurifier.from_host(config.purifier.host, config.purifier.token,
                                  expected_model=EXPECTED_MODEL, verify=verify)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="purifier-control")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("command", choices=("check", "run"))
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        sensor = make_sensor(config)
        if args.command == "check":
            temperature = sensor.read()
            print(f"Platform: {config.platform}")
            print(f"CPU temperature: {temperature:.1f} C")
            print(f"Purifier IP: {config.purifier.host}")
            info = None
            try:
                purifier = make_purifier(config, verify=False)
                info = purifier.verify_model()
                purifier.read_status()
            except PurifierModelMismatch as mismatch:
                print(f"Internal model: {mismatch.reported_model}")
                print("Connection: connected")
                print("Model verification: mismatch")
                return 1
            except PurifierError:
                print(f"Internal model: {info.model if info is not None else 'unavailable'}")
                print("Connection: disconnected")
                return 1
            print(f"Internal model: {info.model}")
            print("Connection: connected")
            return 0

        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
        purifier = make_purifier(config, verify=False)
        Runner(sensor, purifier, TemperaturePolicy(config.control),
               sample_interval_seconds=config.system.sample_interval_seconds).run()
        return 0
    except (ValueError, OSError, SensorError, PurifierError):
        print("Check failed: configuration, sensor, or purifier is unavailable")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
