"""GitLab-Connector über die REST API v4.

Auth: Personal-/Group-Access-Token im Header 'PRIVATE-TOKEN'.

Modell bei dieser Installation: Pro Server/Netzwerkgerät existiert ein
eigenes GitLab-Projekt, gruppiert unter bestimmten Gruppenpfaden (z.B.
"it-services/Hardware/Server"). Diese Pfade werden inkl. Untergruppen
nach Projekten durchsucht; jedes gefundene Projekt gilt als ein Gerät.
Es gibt keine IP/Betriebssystem-Information aus GitLab - hier zählt nur
Existenz/Vollständigkeit (ist für den Server ein Dokumentations-Projekt
vorhanden).

GITLAB_URL ist die Basis-URL der Instanz, z.B. https://gitlab.example.com
(OHNE /api/v4 - wird hier angehängt).
"""
from urllib.parse import quote

import httpx

from app.config import Settings
from app.connectors.base import Connector, ConnectorError
from app.models import Device, DeviceStatus, SourceName

PER_PAGE = 100


class GitlabConnector(Connector):
    name = SourceName.gitlab

    def __init__(self, settings: Settings, group_paths: list[str] | None = None, include_archived: bool = False):
        self.settings = settings
        self.group_paths = group_paths or []
        self.include_archived = include_archived

    def is_configured(self) -> bool:
        return self.settings.gitlab_configured

    def _headers(self) -> dict:
        return {"PRIVATE-TOKEN": self.settings.gitlab_api_token}

    async def _get(self, client: httpx.AsyncClient, path: str, params: dict) -> list:
        url = f"{self.settings.gitlab_url.rstrip('/')}/api/v4{path}"
        try:
            resp = await client.get(url, params=params, headers=self._headers(), timeout=30)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:200]
            raise ConnectorError(f"GitLab API-Fehler (HTTP {exc.response.status_code}): {detail}") from exc
        except httpx.HTTPError as exc:
            raise ConnectorError(f"GitLab nicht erreichbar: {exc}") from exc
        try:
            return resp.json()
        except ValueError as exc:
            preview = resp.text[:200].replace("\n", " ")
            raise ConnectorError(
                f"GitLab hat kein JSON geliefert (HTTP {resp.status_code}). "
                f"Prüfe, ob GITLAB_URL auf die Basis-URL der Instanz zeigt. Antwort: {preview!r}"
            ) from exc

    async def _list_group_projects(self, client: httpx.AsyncClient, group_path: str) -> list[dict]:
        encoded = quote(group_path, safe="")
        projects: list[dict] = []
        page = 1
        params: dict = {"include_subgroups": "true", "per_page": PER_PAGE}
        if not self.include_archived:
            params["archived"] = "false"
        while True:
            batch = await self._get(client, f"/groups/{encoded}/projects", {**params, "page": page})
            if not isinstance(batch, list):
                break
            projects.extend(batch)
            if len(batch) < PER_PAGE:
                break
            page += 1
        return projects

    async def fetch_devices(self) -> list[Device]:
        if not self.is_configured():
            raise ConnectorError("GitLab ist nicht konfiguriert (URL/API-Token fehlen)")
        if not self.group_paths:
            raise ConnectorError("Keine GitLab-Gruppenpfade konfiguriert (Einstellungen -> Filter je Quelle)")

        devices: list[Device] = []
        seen_ids: set[int] = set()
        async with httpx.AsyncClient(verify=self.settings.gitlab_verify_ssl) as client:
            for group_path in self.group_paths:
                projects = await self._list_group_projects(client, group_path)
                for project in projects:
                    if project["id"] in seen_ids:
                        continue
                    seen_ids.add(project["id"])
                    name = project.get("name")
                    path = project.get("path")
                    match_aliases = [path] if path and path != name else []
                    devices.append(
                        Device(
                            source=SourceName.gitlab,
                            source_id=str(project["id"]),
                            hostname=name,
                            status=DeviceStatus.unknown,
                            device_type="gitlab-project",
                            raw_url=project.get("web_url"),
                            match_aliases=match_aliases,
                        )
                    )
        return devices
