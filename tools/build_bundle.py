"""Build a private-data-free portable directory bundle."""

from __future__ import annotations

import platform as platform_module
import re
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path
from typing import Callable


PUBLIC_TEMPLATE = (
    'platform = "macos"\n\n'
    '[purifier]\n'
    'host = "192.168.250.118"\n'
    'token_file = ".secrets/purifier-token"\n\n'
    '[system]\n'
    'temperature_sensor = "cpu"\n'
    'sample_interval_seconds = 5\n\n'
    '[control]\n'
    'high_temperature_c = 60\n'
    'high_duration_seconds = 15\n'
    'recover_temperature_c = 55\n'
    'recover_duration_seconds = 120\n'
    'high_favorite_level = 17\n'
    'low_favorite_level = 3\n'
)
PUBLIC_DEFAULTS = tomllib.loads(PUBLIC_TEMPLATE)


def _validated_template(source: Path, target_platform: str) -> str:
    path = source / "config.example.toml"
    if path.is_symlink() or not path.is_file():
        raise ValueError("config.example.toml must be a regular public file")
    text = path.read_text(encoding="utf-8")
    if re.search(r"[0-9a-fA-F]{32}", text):
        raise ValueError("config.example.toml contains a token-like value")
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        raise ValueError("config.example.toml must be valid public TOML") from None
    if data != PUBLIC_DEFAULTS:
        raise ValueError("config.example.toml contains fields or values outside public defaults")
    return PUBLIC_TEMPLATE.replace('platform = "macos"', f'platform = "{target_platform}"', 1)


def _validate_target(target_platform: str, arch: str) -> None:
    if target_platform == "macos":
        if sys.platform != "darwin" or arch != platform_module.machine():
            raise ValueError("macOS bundles require the native macOS architecture")
    elif target_platform == "windows":
        if sys.platform != "win32" or arch != "x64" or platform_module.machine().lower() not in {
            "amd64", "x86_64"
        }:
            raise ValueError("Windows bundles require a Windows x64 build machine")
    else:
        raise ValueError(f"unsupported bundle platform: {target_platform}")


def _launcher(target_platform: str, command: str) -> str:
    if target_platform == "windows":
        return ("@echo off\nsetlocal\nset \"BUNDLE_DIR=%~dp0\"\n"
                "set \"PATH=%BUNDLE_DIR%bin;%PATH%\"\n"
                f'"%BUNDLE_DIR%app\\purifier-control.exe" --config '
                f'"%BUNDLE_DIR%config.toml" {command}\n')
    return ('#!/bin/sh\nBUNDLE_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"\n'
            'PATH="$BUNDLE_DIR/bin:$PATH" '
            f'"$BUNDLE_DIR/app/purifier-control" --config '
            f'"$BUNDLE_DIR/config.toml" {command}\n')


def _collect_macos_probe(bin_dir: Path, run_command: Callable[[list[str]], str | None]) -> None:
    located = shutil.which("smctemp")
    if located is None:
        raise RuntimeError("smctemp is required to build a macOS bundle")
    executable = Path(located).resolve()
    if not executable.is_file():
        raise RuntimeError("smctemp executable is missing")
    license_file = executable.parent.parent / "LICENSE"
    if not license_file.is_file() or not license_file.read_bytes().strip():
        raise RuntimeError("smctemp license material is missing")

    linkage = run_command(["otool", "-L", str(executable)])
    if not isinstance(linkage, str):
        raise RuntimeError("could not inspect smctemp dependencies with otool")
    dependencies = [line.strip().split(" (", 1)[0] for line in linkage.splitlines()[1:]
                    if line.strip()]
    if not dependencies:
        raise RuntimeError("could not inspect smctemp dependencies with otool")
    for dependency in dependencies:
        if not dependency.startswith(("/System/Library/", "/usr/lib/")):
            raise RuntimeError(f"smctemp has non-system dependency: {dependency}")

    shutil.copy2(executable, bin_dir / "smctemp")
    shutil.copy2(license_file, bin_dir / "LICENSE.smctemp")


def build_bundle(
    source: Path,
    output: Path,
    platform: str,
    arch: str,
    *,
    run_command: Callable[[list[str]], str | None],
) -> Path:
    """Stage a public-only bundle and publish it after every step succeeds."""
    _validate_target(platform, arch)
    if output.exists() or output.is_symlink():
        raise FileExistsError(f"bundle output already exists: {output}")
    template = _validated_template(source, platform)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".bundle-", dir=output.parent) as temporary:
        staging = Path(temporary) / "bundle"
        staging.mkdir()
        (staging / "bin").mkdir()
        if platform == "macos":
            root = Path(temporary)
            dist_path = root / "pyinstaller-dist"
            run_command([
                sys.executable, "-m", "PyInstaller", "--onedir", "--console",
                "--name", "purifier-control", "--distpath", str(dist_path),
                "--workpath", str(root / "pyinstaller-work"),
                "--specpath", str(root / "pyinstaller-spec"),
                str(source / "tools" / "packaged_entry.py"),
            ])
            built_app = dist_path / "purifier-control"
            if not (built_app / "purifier-control").is_file():
                raise RuntimeError("bundle app executable was not produced")
            shutil.move(str(built_app), str(staging / "app"))
            _collect_macos_probe(staging / "bin", run_command)
            executable = staging / "app" / "purifier-control"
        else:
            (staging / "app").mkdir()
            executable = staging / "app" / "purifier-control.exe"
            run_command(["build-app", str(executable)])
        if not executable.is_file():
            raise RuntimeError("bundle app executable was not produced")

        (staging / "config.example.toml").write_text(template, encoding="utf-8")

        suffix = ".cmd" if platform == "windows" else ".command"
        for command in ("check", "run"):
            script = staging / f"{command}{suffix}"
            script.write_text(_launcher(platform, command), encoding="utf-8")
            if platform == "macos":
                script.chmod(0o755)

        (staging / "README.txt").write_text(
            "Portable purifier-control bundle\n\n"
            "Copy config.example.toml to config.toml and set the purifier IP.\n"
            "Create .secrets/purifier-token with your own device token.\n"
            "Run check first; it reads status without changing the device.\n"
            "Run run only while present. Stop with Ctrl+C.\n"
            "Stopping does not restore the purifier's previous state.\n",
            encoding="utf-8",
        )
        staging.rename(output)
    return output
