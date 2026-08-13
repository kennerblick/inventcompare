"""Zabbix-Connector über die JSON-RPC API.

Auth: bevorzugt API-Token (Administration -> API-Tokens, Zabbix >= 5.4),
gesendet als 'Authorization: Bearer <token>' Header. Falls kein Token
gesetzt ist, wird per user.login (Username/Passwort) ein Session-Token
geholt und als 'auth'-Feld im Request-Body mitgeschickt (funktioniert bei
älteren Zabbix-Versionen; bei sehr neuen Versionen ggf. Token verwenden).
"""
import httpx

from app.config import Settings
from app.connectors.base import Connector, ConnectorError
from app.models import Device, DeviceStatus, SourceName


class ZabbixConnector(Connector):
    name = SourceName.zabbix

    def __init__(self, settings: Settings, host_groups: list[str] | None = None):
        self.settings = settings
        self.host_groups = host_groups or []
        self._request_id = 0

    def is_configured(self) -> bool:
        return self.settings.zabbix_configured

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    async def _call(self, client: httpx.AsyncClient, method: str, params: dict, auth_token: str | None = None) -> dict:
        body = {"jsonrpc": "2.0", "method": method, "params": params, "id": self._next_id()}
        headers = {"Content-Type": "application/json-rpc"}
        if self.settings.zabbix_api_token:
            headers["Authorization"] = f"Bearer {self.settings.zabbix_api_token}"
        elif auth_token:
            body["auth"] = auth_token
        try:
            resp = await client.post(self.settings.zabbix_url, json=body, headers=headers, timeout=30)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            raise ConnectorError(f"Zabbix nicht erreichbar: {exc}") from exc
        try:
            data = resp.json()
        except ValueError as exc:
            preview = resp.text[:200].replace("\n", " ")
            raise ConnectorError(
                f"Zabbix hat kein JSON geliefert (HTTP {resp.status_code}). "
                f"Prüfe, ob ZABBIX_URL auf den api_jsonrpc.php-Endpunkt zeigt. Antwort: {preview!r}"
            ) from exc
        if "error" in data:
            raise ConnectorError(f"Zabbix API-Fehler: {data['error'].get('data') or data['error'].get('message')}")
        return data["result"]

    async def _login(self, client: httpx.AsyncClient) -> str | None:
        if self.settings.zabbix_api_token:
            return None
        result = await self._call(
            client,
            "user.login",
            {"username": self.settings.zabbix_user, "password": self.settings.zabbix_password},
        )
        return result

    async def fetch_devices(self) -> list[Device]:
        if not self.is_configured():
            raise ConnectorError("Zabbix ist nicht konfiguriert (URL/Zugangsdaten fehlen)")

        async with httpx.AsyncClient(verify=self.settings.zabbix_verify_ssl) as client:
            auth_token = await self._login(client)

            params: dict = {
                "output": ["hostid", "host", "name", "status"],
                "selectInterfaces": ["ip", "available"],
                "selectInventory": ["os", "os_full"],
            }
            if self.host_groups:
                # Alle Gruppen holen und clientseitig auf exakten Namen oder
                # verschachtelte Untergruppe (Zabbix-Konvention "Parent/Child")
                # filtern - z.B. schließt "Server" auch "Server/Linux" ein,
                # aber nicht eine unabhängige Gruppe "Serverraum".
                all_groups = await self._call(client, "hostgroup.get", {"output": ["groupid", "name"]}, auth_token)
                groupids = [
                    g["groupid"]
                    for g in all_groups
                    if any(g["name"] == wanted or g["name"].startswith(wanted + "/") for wanted in self.host_groups)
                ]
                if groupids:
                    params["groupids"] = groupids

            hosts = await self._call(client, "host.get", params, auth_token)

        devices: list[Device] = []
        for host in hosts:
            interfaces = host.get("interfaces") or []
            ip = interfaces[0]["ip"] if interfaces else None
            available = interfaces[0].get("available") if interfaces else None
            # available: 0=unknown, 1=erreichbar, 2=nicht erreichbar
            if available == "1":
                status = DeviceStatus.up
            elif available == "2":
                status = DeviceStatus.down
            else:
                status = DeviceStatus.unknown

            inventory = host.get("inventory") or {}
            os_name = inventory.get("os_full") or inventory.get("os") or None

            technical_name = host.get("host") or host.get("name")
            visible_name = host.get("name")
            match_aliases = [visible_name] if visible_name and visible_name != technical_name else []

            devices.append(
                Device(
                    source=SourceName.zabbix,
                    source_id=host["hostid"],
                    hostname=technical_name,
                    ip=ip,
                    os=os_name or None,
                    status=status,
                    device_type="host",
                    match_aliases=match_aliases,
                )
            )
        return devices
