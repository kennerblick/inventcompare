from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class SourceName(str, Enum):
    zabbix = "zabbix"
    idoit = "idoit"


class DeviceStatus(str, Enum):
    """Live-Status, soweit von der Quelle gemeldet (z.B. Zabbix)."""

    up = "up"
    down = "down"
    unknown = "unknown"


class Device(BaseModel):
    """Normalisierte Sicht auf ein Gerät (Server/Netzwerkgerät) aus einer Quelle."""

    source: SourceName
    source_id: str
    hostname: str
    ip: Optional[str] = None
    os: Optional[str] = None
    status: DeviceStatus = DeviceStatus.unknown
    device_type: Optional[str] = None
    raw_url: Optional[str] = None
    match_aliases: list[str] = []
    """Zusätzliche Namen (z.B. FQDN aus einer IP-Zuordnung), unter denen dieses
    Gerät beim Abgleich ebenfalls gefunden werden soll, zusätzlich zu hostname."""


class FieldDiff(BaseModel):
    field: str
    values: dict[str, Optional[str]]  # source-name -> value


class MatchStatus(str, Enum):
    match = "match"
    field_mismatch = "field_mismatch"
    missing = "missing"


class ComparisonEntry(BaseModel):
    """Ein abgeglichenes Gerät (per Hostname/IP über Quellen hinweg vereinigt)."""

    key: str  # normalisierter Hostname, dient als Matching-Schlüssel
    hostname: str
    present_in: list[SourceName]
    missing_in: list[SourceName]
    status: MatchStatus
    diffs: list[FieldDiff] = []
    devices: dict[str, Device] = {}  # source-name -> Device


class SourceStatus(BaseModel):
    name: SourceName
    configured: bool
    reachable: Optional[bool] = None
    device_count: Optional[int] = None
    error: Optional[str] = None
    last_sync: Optional[datetime] = None


class ComparisonSnapshot(BaseModel):
    generated_at: datetime
    sources: list[SourceStatus]
    entries: list[ComparisonEntry]
    summary: dict[str, int]
