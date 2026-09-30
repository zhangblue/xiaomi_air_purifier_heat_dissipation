"""Build a private-data-free portable directory bundle."""

from __future__ import annotations

import hashlib
import json
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
SMCTEMP_VERSION = "0.7.0"
SMCTEMP_SOURCE_URL = "https://github.com/narugit/smctemp/archive/refs/tags/0.7.0.tar.gz"
SMCTEMP_SOURCE_SHA256 = "4ca4eaade1964f2d4d39c5fc21ccb357a1966c5c2b8bb1480b08a28d47f8d4dd"
SMCTEMP_LICENSE_SHA256 = "ab15fd526bd8dd18a9e77ebc139656bf4d33e97fc7238cd11bf60e2b9b8666c6"
# The arm64 binary was built from the pinned Homebrew source on the verified build host.
# Other build architectures or binary revisions require a separate provenance review.
SMCTEMP_BINARY_SHA256 = {
    "arm64": "80c81fe8a5f66a9b4b27de09b376930ca1b940230c29fcbc9d89f1e38d520487",
}


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _collect_macos_probe(bin_dir: Path, run_command: Callable[[list[str]], str | None]) -> None:
    located = shutil.which("smctemp")
    if located is None:
        raise RuntimeError("smctemp is required to build a macOS bundle")
    executable = Path(located).resolve()
    if not executable.is_file():
        raise RuntimeError("smctemp executable is missing")
    keg = executable.parent.parent
    if (executable.parent.name != "bin" or executable.name != "smctemp" or
            keg.name != SMCTEMP_VERSION or keg.parent.name != "smctemp" or
            keg.parent.parent.name != "Cellar"):
        raise RuntimeError("unverified smctemp binary location")
    expected_binary_hash = SMCTEMP_BINARY_SHA256.get(platform_module.machine())
    if expected_binary_hash is None or _sha256(executable) != expected_binary_hash:
        raise RuntimeError("unverified smctemp binary")
    if run_command([str(executable), "-v"]) != f"{SMCTEMP_VERSION}\n":
        raise RuntimeError("unverified smctemp binary version")

    try:
        receipt = json.loads((keg / "INSTALL_RECEIPT.json").read_text(encoding="utf-8"))
        source_record = receipt["source"]
        receipt_ok = (source_record["tap"] == "narugit/tap" and
                      source_record["versions"]["stable"] == SMCTEMP_VERSION and
                      receipt["arch"] == platform_module.machine() and
                      receipt["built_as_bottle"] is False and
                      receipt["poured_from_bottle"] is False)
    except (OSError, ValueError, KeyError, TypeError):
        receipt_ok = False
    if not receipt_ok:
        raise RuntimeError("unverified smctemp installation receipt")

    try:
        formula = (keg / ".brew" / "smctemp.rb").read_text(encoding="utf-8")
    except OSError:
        raise RuntimeError("smctemp source formula is missing") from None
    fields = re.findall(r'^\s*(url|sha256|license)\s+"([^"]+)"\s*$', formula, re.MULTILINE)
    if len(fields) != 3 or dict(fields) != {
        "url": SMCTEMP_SOURCE_URL,
        "sha256": SMCTEMP_SOURCE_SHA256,
        "license": "GPL-2.0-only",
    }:
        raise RuntimeError("smctemp source formula is unverified")

    license_file = keg / "LICENSE"
    if not license_file.is_file() or _sha256(license_file) != SMCTEMP_LICENSE_SHA256:
        raise RuntimeError("smctemp license material is missing or unverified")

    source_cache = run_command(["brew", "--cache", "smctemp"])
    if not isinstance(source_cache, str) or not source_cache.strip():
        raise RuntimeError("smctemp source archive is missing")
    archive = Path(source_cache.strip())
    if not archive.is_file() or _sha256(archive) != SMCTEMP_SOURCE_SHA256:
        raise RuntimeError("smctemp source archive is missing or unverified")

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
    shutil.copy2(archive, bin_dir / "smctemp-0.7.0-source.tar.gz")


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
            "macOS: smctemp GPL-2.0-only license and version 0.7.0 source "
            "archive are in bin/.\n"
            "Run check first; it reads status without changing the device.\n"
            "Run run only while present. Stop with Ctrl+C.\n"
            "Stopping does not restore the purifier's previous state.\n",
            encoding="utf-8",
        )
        staging.rename(output)
    return output
