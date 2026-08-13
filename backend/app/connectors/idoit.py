"""i-doit-Connector über die JSON-RPC API.

Auth: apikey (Mandant/App-Schlüssel aus i-doit -> Systembibliothek ->
Mandanten) im Request-Body sowie HTTP Basic-Auth (Username/Passwort)
auf dem HTTP-Request. Ist die i-doit-Einstellung
'api.authenticated-users-only' aktiv, verlangt i-doit ausdrücklich HTTP
Basic-Auth oder eine Session-ID; kein Login/Session-Handling nötig, da
hier bei jedem Request Basic-Auth mitgesendet wird. Bewusst KEINE
zusätzlichen 'X-RPC-Auth-*'-Header, da diese bei manchen i-doit-Versionen
mit der Basic-Auth kollidieren und den Login fehlschlagen lassen.

IDOIT_URL muss auf den JSON-RPC-Endpunkt zeigen, z.B.
https://idoit.example.com/src/jsonrpc.php

Objekte werden per cmdb.objects.read gelistet und je Objekt über
cmdb.category.read um IP (C__CATG__IP) und Betriebssystem (C__CATG__OS)
ergänzt. Je nach i-doit-Version/Individualisierung können Attributnamen
in den Kategorien leicht abweichen - bei Bedarf hier anpassen.
"""
import asyncio

import httpx

from app.config import Settings
from app.connectors.base import Connector, ConnectorError
from app.models import Device, DeviceStatus, SourceName

CONCURRENCY_LIMIT = 8


def _as_text(value) -> str | None:
    """i-doit liefert manche Kategorie-Felder als reinen String, andere als
    Objekt-Referenz (dict mit u.a. 'title'/'id') - je nach i-doit-Version und
    Konfiguration. Diese Funktion holt in beiden Fällen den Anzeigetext."""
    if value is None:
        return None
    if isinstance(value, str):
        return value or None
    if isinstance(value, dict):
        return value.get("title") or value.get("ref_title") or None
    return str(value)


class IdoitConnector(Connector):
    name = SourceName.idoit

    def __init__(self, settings: Settings, object_types: list[str] | None = None):
        self.settings = settings
        self.object_types = object_types or []
        self._request_id = 0

    def is_configured(self) -> bool:
        return self.settings.idoit_configured

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _call(self, client: httpx.AsyncClient, method: str, params: dict) -> dict | list:
        body = {
            "version": "2.0",
            "method": method,
            "params": {**params, "apikey": self.settings.idoit_api_key},
            "id": self._next_id(),
        }
        try:
            resp = await client.post(self.settings.idoit_url, json=body, headers={"Content-Type": "application/json"}, timeout=30)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ConnectorError(f"i-doit nicht erreichbar: {exc}") from exc
        try:
            data = resp.json()
        except ValueError as exc:
            preview = resp.text[:200].replace("\n", " ")
            raise ConnectorError(
                f"i-doit hat kein JSON geliefert (HTTP {resp.status_code}). "
                f"Prüfe, ob IDOIT_URL auf den jsonrpc.php-Endpunkt zeigt. Antwort: {preview!r}"
            ) from exc
        if "error" in data:
            raise ConnectorError(f"i-doit API-Fehler: {data['error'].get('data') or data['error'].get('message')}")
        return data["result"]

    async def _fetch_category(self, client: httpx.AsyncClient, sem: asyncio.Semaphore, object_id: int, category: str) -> list:
        async with sem:
            try:
                result = await self._call(client, "cmdb.category.read", {"objID": object_id, "category": category})
            except ConnectorError:
                return []
            return result or []

    async def fetch_devices(self) -> list[Device]:
        if not self.is_configured():
            raise ConnectorError("i-doit ist nicht konfiguriert (URL/API-Key fehlen)")

        basic_auth = None
        if self.settings.idoit_user and self.settings.idoit_password:
            basic_auth = httpx.BasicAuth(self.settings.idoit_user, self.settings.idoit_password)

        async with httpx.AsyncClient(verify=self.settings.idoit_verify_ssl, auth=basic_auth) as client:
            filter_: dict = {}
            if self.object_types:
                filter_["type"] = self.object_types
            objects = await self._call(
                client,
                "cmdb.objects.read",
                {"filter": filter_} if filter_ else {},
            )

            sem = asyncio.Semaphore(CONCURRENCY_LIMIT)
            ip_results, os_results = await asyncio.gather(
                asyncio.gather(*[self._fetch_category(client, sem, obj["id"], "C__CATG__IP") for obj in objects]),
                asyncio.gather(*[self._fetch_category(client, sem, obj["id"], "C__CATG__OS") for obj in objects]),
            )

        devices: list[Device] = []
        for obj, ip_entries, os_entries in zip(objects, ip_results, os_results):
            ip = None
            if ip_entries:
                primary = next((e for e in ip_entries if e.get("primary")), ip_entries[0])
                ip = _as_text(primary.get("hostaddress")) or _as_text(primary.get("ipv4_address")) or _as_text(primary.get("ipv6_address"))

            os_name = None
            if os_entries:
                entry = os_entries[0]
                os_name = _as_text(entry.get("title")) or _as_text(entry.get("manufacturer"))

            devices.append(
                Device(
                    source=SourceName.idoit,
                    source_id=str(obj["id"]),
                    hostname=obj.get("title"),
                    ip=ip,
                    os=os_name,
                    status=DeviceStatus.unknown,
                    device_type=obj.get("type_title") or obj.get("type"),
                )
            )
        return devices
