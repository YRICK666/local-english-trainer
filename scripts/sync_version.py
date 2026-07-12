from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VERSION_JSON = ROOT / "version.json"
BACKEND_VERSION = ROOT / "backend" / "app" / "version.py"
FRONTEND_PACKAGE = ROOT / "frontend" / "package.json"

APP_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
PACKAGE_VERSION_RE = re.compile(r'("version"\s*:\s*")([^"]+)(")', re.M)
BACKEND_PATTERNS = {
    "APP_VERSION": re.compile(r'^(APP_VERSION\s*=\s*")([^"]+)(")', re.M),
    "API_PROTOCOL_VERSION": re.compile(r"^(API_PROTOCOL_VERSION\s*=\s*)(\d+)", re.M),
    "SCHEMA_VERSION": re.compile(r"^(SCHEMA_VERSION\s*=\s*)(\d+)", re.M),
}


def load_version_contract() -> dict[str, Any]:
    try:
        data = json.loads(VERSION_JSON.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError("version.json is missing") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"version.json is invalid JSON: {exc}") from exc

    app_version = data.get("app_version")
    api_protocol_version = data.get("api_protocol_version")
    schema_version = data.get("schema_version")

    if not isinstance(app_version, str) or not APP_VERSION_RE.fullmatch(app_version):
        raise ValueError("version.json app_version must be a semantic version string")
    if not isinstance(api_protocol_version, int) or api_protocol_version <= 0:
        raise ValueError("version.json api_protocol_version must be a positive integer")
    if not isinstance(schema_version, int) or schema_version <= 0:
        raise ValueError("version.json schema_version must be a positive integer")

    return {
        "app_version": app_version,
        "api_protocol_version": api_protocol_version,
        "schema_version": schema_version,
    }


def read_backend_values() -> dict[str, Any]:
    namespace: dict[str, Any] = {}
    exec(BACKEND_VERSION.read_text(encoding="utf-8"), namespace)
    return {
        "app_version": namespace.get("APP_VERSION"),
        "api_protocol_version": namespace.get("API_PROTOCOL_VERSION"),
        "schema_version": namespace.get("SCHEMA_VERSION"),
    }


def read_frontend_version() -> str:
    data = json.loads(FRONTEND_PACKAGE.read_text(encoding="utf-8"))
    value = data.get("version")
    if not isinstance(value, str):
        raise ValueError("frontend/package.json version must be a string")
    return value


def replace_required(pattern: re.Pattern[str], text: str, replacement: str, label: str) -> str:
    updated, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise ValueError(f"could not update {label}")
    return updated


def write_backend(contract: dict[str, Any]) -> None:
    text = BACKEND_VERSION.read_text(encoding="utf-8")
    text = replace_required(
        BACKEND_PATTERNS["APP_VERSION"],
        text,
        rf'\g<1>{contract["app_version"]}\3',
        "backend APP_VERSION",
    )
    text = replace_required(
        BACKEND_PATTERNS["API_PROTOCOL_VERSION"],
        text,
        rf'\g<1>{contract["api_protocol_version"]}',
        "backend API_PROTOCOL_VERSION",
    )
    text = replace_required(
        BACKEND_PATTERNS["SCHEMA_VERSION"],
        text,
        rf'\g<1>{contract["schema_version"]}',
        "backend SCHEMA_VERSION",
    )
    BACKEND_VERSION.write_text(text, encoding="utf-8", newline="")


def write_frontend(contract: dict[str, Any]) -> None:
    text = FRONTEND_PACKAGE.read_text(encoding="utf-8")
    updated = replace_required(
        PACKAGE_VERSION_RE,
        text,
        rf'\g<1>{contract["app_version"]}\3',
        "frontend package version",
    )
    FRONTEND_PACKAGE.write_text(updated, encoding="utf-8", newline="")


def check(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    backend = read_backend_values()
    frontend_version = read_frontend_version()
    if backend != contract:
        errors.append(f"backend/app/version.py does not match version.json: {backend} != {contract}")
    if frontend_version != contract["app_version"]:
        errors.append(
            "frontend/package.json version does not match version.json: "
            f"{frontend_version} != {contract['app_version']}"
        )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Synchronize checked-in version constants from version.json.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write controlled version fields")
    mode.add_argument("--check", action="store_true", help="verify controlled version fields")
    args = parser.parse_args()

    try:
        contract = load_version_contract()
        if args.write:
            write_backend(contract)
            write_frontend(contract)
        errors = check(contract)
    except Exception as exc:  # noqa: BLE001 - command-line script reports concise failures.
        print(f"version sync failed: {exc}", file=sys.stderr)
        return 1

    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("version contract is in sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())