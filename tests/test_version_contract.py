from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from backend.app.main import health
from backend.app.version import API_PROTOCOL_VERSION, APP_VERSION, SCHEMA_VERSION

ROOT = Path(__file__).resolve().parents[1]
VERSION_JSON = ROOT / "version.json"
PACKAGE_JSON = ROOT / "frontend" / "package.json"
SYNC_SCRIPT = ROOT / "scripts" / "sync_version.py"


def load_contract() -> dict[str, object]:
    return json.loads(VERSION_JSON.read_text(encoding="utf-8"))


def test_version_json_exists() -> None:
    assert VERSION_JSON.is_file()


def test_version_json_values_are_valid() -> None:
    contract = load_contract()

    assert re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", contract["app_version"])
    assert isinstance(contract["api_protocol_version"], int)
    assert contract["api_protocol_version"] > 0
    assert isinstance(contract["schema_version"], int)
    assert contract["schema_version"] > 0


def test_version_json_matches_backend_constants() -> None:
    contract = load_contract()

    assert contract["app_version"] == APP_VERSION
    assert contract["api_protocol_version"] == API_PROTOCOL_VERSION
    assert contract["schema_version"] == SCHEMA_VERSION


def test_version_json_matches_frontend_package_version() -> None:
    contract = load_contract()
    package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))

    assert package["version"] == contract["app_version"]


def test_sync_version_check_succeeds_without_tauri_files() -> None:
    assert not (ROOT / "src-tauri" / "tauri.conf.json").exists()
    assert not (ROOT / "src-tauri" / "Cargo.toml").exists()

    result = subprocess.run(
        [sys.executable, str(SYNC_SCRIPT), "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_health_versions_match_python_constants() -> None:
    response = health()

    assert response.app_version == APP_VERSION
    assert response.api_protocol_version == API_PROTOCOL_VERSION
    assert response.schema_version == SCHEMA_VERSION