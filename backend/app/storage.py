"""JSON-Dateispeicher für nicht-sensible Einstellungen und den letzten
Vergleichs-Snapshot. Keine Zugangsdaten hier ablegen - die kommen aus der
Umgebung (siehe config.py)."""
import json
from pathlib import Path
from threading import Lock
from typing import Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

SETTINGS_FILE = DATA_DIR / "settings.json"
SNAPSHOT_FILE = DATA_DIR / "comparison_snapshot.json"

DEFAULT_SETTINGS: dict[str, Any] = {
    "sync_interval_minutes": 15,
    "sources_enabled": {"zabbix": True, "idoit": True},
    "matching": {
        # Reihenfolge der Matching-Strategie: erst Hostname, dann IP
        "match_on": ["hostname", "ip"],
        "ignore_case": True,
        "strip_domain": True,
    },
    "idoit": {
        # i-doit Objekttypen, die als "Server/Netzwerkgerät" gelten.
        # Kann in einer i-doit-Installation individuell abweichen, daher
        # über die Oberfläche anpassbar.
        "object_types": ["C__OBJTYPE__SERVER", "C__OBJTYPE__NETWORK_DEVICE", "C__OBJTYPE__VIRTUAL_SERVER"],
    },
    "zabbix": {
        # Zabbix Host-Gruppen, die einbezogen werden sollen (leer = alle)
        "host_groups": [],
    },
}

_lock = Lock()


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data: Any) -> None:
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    tmp.replace(path)


def get_settings_data() -> dict[str, Any]:
    with _lock:
        data = _read_json(SETTINGS_FILE, {})
        merged = _deep_merge(DEFAULT_SETTINGS, data)
        if not SETTINGS_FILE.exists():
            _write_json(SETTINGS_FILE, merged)
        return merged


def save_settings_data(data: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        current = _read_json(SETTINGS_FILE, {})
        merged = _deep_merge(_deep_merge(DEFAULT_SETTINGS, current), data)
        _write_json(SETTINGS_FILE, merged)
        return merged


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_snapshot() -> dict[str, Any] | None:
    with _lock:
        return _read_json(SNAPSHOT_FILE, None)


def save_snapshot(snapshot: dict[str, Any]) -> None:
    with _lock:
        _write_json(SNAPSHOT_FILE, snapshot)
