"""Konfiguration aus Umgebungsvariablen (.env auf dem Docker-Host).

Zugangsdaten für die Quellsysteme werden ausschließlich hier aus der
Umgebung gelesen und NIE über die Web-Oberfläche gesetzt oder dort
angezeigt. Nicht-sensible Einstellungen (Sync-Intervall, Feld-Mapping,
aktivierte Quellen) liegen dagegen in `data/settings.json` und sind über
die Web-Oberfläche änderbar (siehe app/storage.py).
"""
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Zabbix
    zabbix_url: Optional[str] = None
    zabbix_api_token: Optional[str] = None
    zabbix_user: Optional[str] = None
    zabbix_password: Optional[str] = None
    zabbix_verify_ssl: bool = True

    # i-doit
    idoit_url: Optional[str] = None
    idoit_api_key: Optional[str] = None
    idoit_user: Optional[str] = None
    idoit_password: Optional[str] = None
    idoit_verify_ssl: bool = True

    @property
    def zabbix_configured(self) -> bool:
        return bool(self.zabbix_url and (self.zabbix_api_token or (self.zabbix_user and self.zabbix_password)))

    @property
    def idoit_configured(self) -> bool:
        return bool(self.idoit_url and self.idoit_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
