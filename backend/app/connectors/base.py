from abc import ABC, abstractmethod

from app.models import Device, SourceName, SourceStatus


class ConnectorError(Exception):
    """Wird bei nicht erreichbarer/fehlerhaft konfigurierter Quelle geworfen."""


class Connector(ABC):
    name: SourceName

    @abstractmethod
    def is_configured(self) -> bool:
        """True, wenn genügend Zugangsdaten aus der Umgebung vorhanden sind."""

    @abstractmethod
    async def fetch_devices(self) -> list[Device]:
        """Liefert alle Geräte dieser Quelle. Wirft ConnectorError bei Fehlern."""

    async def status(self) -> SourceStatus:
        if not self.is_configured():
            return SourceStatus(name=self.name, configured=False, reachable=None)
        try:
            devices = await self.fetch_devices()
            return SourceStatus(
                name=self.name,
                configured=True,
                reachable=True,
                device_count=len(devices),
            )
        except ConnectorError as exc:
            return SourceStatus(name=self.name, configured=True, reachable=False, error=str(exc))
