import asyncio
import logging
from datetime import datetime, timezone

from app.comparison import compare
from app.config import Settings, get_settings
from app.connectors.idoit import IdoitConnector
from app.connectors.zabbix import ZabbixConnector
from app.connectors.base import ConnectorError
from app.models import ComparisonSnapshot, SourceStatus
from app import storage

logger = logging.getLogger("inventcompare.sync")

_sync_lock = asyncio.Lock()


def build_connectors(settings: Settings, config: dict):
    sources_enabled = config.get("sources_enabled", {})
    connectors = []
    if sources_enabled.get("zabbix", True):
        connectors.append(ZabbixConnector(settings, host_groups=config.get("zabbix", {}).get("host_groups")))
    if sources_enabled.get("idoit", True):
        connectors.append(IdoitConnector(settings, object_types=config.get("idoit", {}).get("object_types")))
    return connectors


async def run_sync() -> ComparisonSnapshot:
    """Führt einen vollständigen Sync + Vergleich aus und speichert das Ergebnis."""
    async with _sync_lock:
        settings = get_settings()
        config = storage.get_settings_data()
        connectors = build_connectors(settings, config)

        devices_by_source = {}
        statuses: list[SourceStatus] = []
        now = datetime.now(timezone.utc)

        for connector in connectors:
            if not connector.is_configured():
                statuses.append(SourceStatus(name=connector.name, configured=False))
                continue
            try:
                devices = await connector.fetch_devices()
                devices_by_source[connector.name] = devices
                statuses.append(
                    SourceStatus(
                        name=connector.name,
                        configured=True,
                        reachable=True,
                        device_count=len(devices),
                        last_sync=now,
                    )
                )
            except ConnectorError as exc:
                logger.warning("Sync-Fehler bei %s: %s", connector.name, exc)
                statuses.append(SourceStatus(name=connector.name, configured=True, reachable=False, error=str(exc)))
            except Exception as exc:  # unerwarteter Fehler (z.B. abweichendes API-Antwortformat)
                logger.exception("Unerwarteter Fehler bei %s", connector.name)
                statuses.append(
                    SourceStatus(
                        name=connector.name,
                        configured=True,
                        reachable=False,
                        error=f"Unerwarteter Fehler: {exc.__class__.__name__}: {exc}",
                    )
                )

        entries, summary = compare(devices_by_source, config.get("matching", {}))

        snapshot = ComparisonSnapshot(generated_at=now, sources=statuses, entries=entries, summary=summary)
        storage.save_snapshot(snapshot.model_dump(mode="json"))
        return snapshot


def get_last_snapshot() -> ComparisonSnapshot | None:
    data = storage.load_snapshot()
    if data is None:
        return None
    return ComparisonSnapshot.model_validate(data)
