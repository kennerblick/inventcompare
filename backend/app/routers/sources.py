from fastapi import APIRouter, HTTPException

from app import storage
from app.config import get_settings
from app.connectors.base import ConnectorError
from app.connectors.idoit import IdoitConnector
from app.sync_service import build_connectors, get_last_snapshot

router = APIRouter(prefix="/api/sources", tags=["sources"])


@router.get("")
async def list_sources():
    """Konfigurationsstatus je Quelle (aus .env) plus letzter bekannter Sync-Status."""
    settings = get_settings()
    config = storage.get_settings_data()
    connectors = build_connectors(settings, config)

    snapshot = get_last_snapshot()
    last_by_name = {s.name.value: s for s in snapshot.sources} if snapshot else {}

    result = []
    for connector in connectors:
        last = last_by_name.get(connector.name.value)
        result.append(
            {
                "name": connector.name.value,
                "configured": connector.is_configured(),
                "reachable": last.reachable if last else None,
                "device_count": last.device_count if last else None,
                "error": last.error if last else None,
                "last_sync": last.last_sync if last else None,
            }
        )
    return result


@router.post("/{name}/test")
async def test_source(name: str):
    """Testet die Verbindung zu einer einzelnen Quelle, ohne einen vollen Sync auszulösen."""
    settings = get_settings()
    config = storage.get_settings_data()
    connectors = {c.name.value: c for c in build_connectors(settings, config)}
    connector = connectors.get(name)
    if connector is None:
        return {"error": f"Unbekannte Quelle '{name}'"}
    status = await connector.status()
    return status.model_dump(mode="json")


@router.get("/idoit/object-types")
async def list_idoit_object_types():
    """Listet alle in der i-doit-Instanz vorhandenen Objekttypen (const + title),
    damit die passenden Werte für die Objekttyp-Filter-Einstellung gefunden werden."""
    settings = get_settings()
    connector = IdoitConnector(settings)
    if not connector.is_configured():
        raise HTTPException(status_code=400, detail="i-doit ist nicht konfiguriert (URL/API-Key fehlen)")
    try:
        types = await connector.list_object_types()
    except ConnectorError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return sorted(types, key=lambda t: (t.get("title") or "").lower())
