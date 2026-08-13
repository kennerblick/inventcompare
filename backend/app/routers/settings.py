from fastapi import APIRouter
from pydantic import BaseModel

from app import storage
from app.config import get_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    sync_interval_minutes: int | None = None
    sources_enabled: dict[str, bool] | None = None
    matching: dict | None = None
    idoit: dict | None = None
    zabbix: dict | None = None
    gitlab: dict | None = None


@router.get("")
async def get_settings_endpoint():
    """Nicht-sensible Einstellungen. Zugangsdaten kommen ausschließlich aus der .env
    auf dem Docker-Host und werden hier nur als 'ist gesetzt'-Flag angezeigt."""
    settings = get_settings()
    return {
        "config": storage.get_settings_data(),
        "credentials_configured": {
            "zabbix": settings.zabbix_configured,
            "idoit": settings.idoit_configured,
            "gitlab": settings.gitlab_configured,
        },
    }


@router.put("")
async def update_settings(update: SettingsUpdate):
    data = {k: v for k, v in update.model_dump(exclude_none=True).items()}
    merged = storage.save_settings_data(data)
    return {"config": merged}
