"""i-doit-Connector über die JSON-RPC API.

Auth: apikey (Mandant/App-Schlüssel aus i-doit -> Systembibliothek ->
Mandanten) im Request-Body sowie Username/Passwort als Header
'X-RPC-Auth-Username' / 'X-RPC-Auth-Password' bei jedem Aufruf (kein
Login/Session-Handling nötig).

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

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.settings.idoit_user:
            headers["X-RPC-Auth-Username"] = self.settings.idoit_user
        if self.settings.idoit_password:
            headers["X-RPC-Auth-Password"] = self.settings.idoit_password
        return headers

    async def _call(self, client: httpx.AsyncClient, method: str, params: dict) -> dict | list:
        body = {
            "version": "2.0",
            "method": method,
            "params": {**params, "apikey": self.settings.idoit_api_key},
            "id": self._next_id(),
        }
        try:
            resp = await client.post(self.settings.idoit_url, json=body, headers=self._headers(), timeout=30)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ConnectorError(f"i-doit nicht erreichbar: {exc}") from exc
        data = resp.json()
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

        async with httpx.AsyncClient(verify=self.settings.idoit_verify_ssl) as client:
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
                ip = primary.get("hostaddress") or primary.get("ipv4_address") or primary.get("ipv6_address")

            os_name = None
            if os_entries:
                entry = os_entries[0]
                os_name = entry.get("title") or (entry.get("manufacturer") or {}).get("title")

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
