"""Abgleich der Geräte aus mehreren Quellen.

Matching-Strategie (konfigurierbar über settings.matching), in dieser
Reihenfolge, bis ein Gerät verbraucht ist:
1. Normalisierter Hostname ODER einer der 'match_aliases' des Geräts
   (z.B. der FQDN aus einer i-doit-IP-Zuordnung) trifft auf den
   Hostnamen/eine Alias eines Geräts einer anderen Quelle.
2. Für danach noch unverbrauchte Geräte: Versuch über die IP-Adresse.
3. Übrig gebliebene Geräte werden als "nur in dieser Quelle vorhanden"
   (missing) einzeln aufgenommen.

Verglichen werden (soweit in beiden Quellen vorhanden): IP-Adresse und
Betriebssystem. Fehlt ein Gerät komplett in einer Quelle, gilt es als
"missing" (Existenz/Vollständigkeit).
"""
from app.models import ComparisonEntry, Device, FieldDiff, MatchStatus, SourceName


def _normalize_hostname(hostname: str, strip_domain: bool, ignore_case: bool) -> str:
    value = (hostname or "").strip()
    if strip_domain and "." in value:
        value = value.split(".")[0]
    if ignore_case:
        value = value.lower()
    return value


def _normalize_ip(ip: str | None) -> str | None:
    return ip.strip() if ip else None


def compare(devices_by_source: dict[SourceName, list[Device]], matching: dict) -> tuple[list[ComparisonEntry], dict[str, int]]:
    strip_domain = matching.get("strip_domain", True)
    ignore_case = matching.get("ignore_case", True)
    sources = list(devices_by_source.keys())

    # Lookup je Quelle: normalisierter Name (Hostname ODER Alias) -> Device.
    # Ein Gerät kann unter mehreren Schlüsseln auffindbar sein.
    indexed: dict[SourceName, dict[str, Device]] = {}
    for source, devices in devices_by_source.items():
        idx: dict[str, Device] = {}
        for device in devices:
            for raw_name in [device.hostname, *device.match_aliases]:
                key = _normalize_hostname(raw_name, strip_domain, ignore_case)
                if key and key not in idx:
                    idx[key] = device
        indexed[source] = idx

    used: dict[SourceName, set[str]] = {s: set() for s in sources}

    def unused_at(key: str) -> dict[SourceName, Device]:
        result = {}
        for source in sources:
            device = indexed[source].get(key)
            if device is not None and device.source_id not in used[source]:
                result[source] = device
        return result

    all_keys = sorted({k for idx in indexed.values() for k in idx})
    entries: list[ComparisonEntry] = []

    # Pass 1: Name-/Alias-Treffer über mind. zwei Quellen hinweg
    for key in all_keys:
        devices = unused_at(key)
        if len(devices) < 2:
            continue
        for source, device in devices.items():
            used[source].add(device.source_id)
        entries.append(_build_entry(key, devices, sources))

    # Pass 2: verbliebene (noch unverbrauchte) Geräte über IP verknüpfen
    remaining = [
        (source, device)
        for source, devices in devices_by_source.items()
        for device in devices
        if device.source_id not in used[source]
    ]
    for i, (source_a, device_a) in enumerate(remaining):
        if device_a.source_id in used[source_a] or not device_a.ip:
            continue
        for source_b, device_b in remaining[i + 1 :]:
            if source_b == source_a or device_b.source_id in used[source_b]:
                continue
            if device_a.source_id in used[source_a]:
                break
            if device_b.ip and _normalize_ip(device_b.ip) == _normalize_ip(device_a.ip):
                used[source_a].add(device_a.source_id)
                used[source_b].add(device_b.source_id)
                key = _normalize_hostname(device_a.hostname, strip_domain, ignore_case)
                entries.append(_build_entry(key, {source_a: device_a, source_b: device_b}, sources))

    # Pass 3: alles, was übrig bleibt, einzeln als "missing" aufnehmen
    for source, devices in devices_by_source.items():
        for device in devices:
            if device.source_id in used[source]:
                continue
            used[source].add(device.source_id)
            key = _normalize_hostname(device.hostname, strip_domain, ignore_case)
            entries.append(_build_entry(key, {source: device}, sources))

    entries.sort(key=lambda e: e.hostname.lower())

    summary = {
        "total": len(entries),
        "match": sum(1 for e in entries if e.status == MatchStatus.match),
        "field_mismatch": sum(1 for e in entries if e.status == MatchStatus.field_mismatch),
        "missing": sum(1 for e in entries if e.status == MatchStatus.missing),
    }
    return entries, summary


def _build_entry(key: str, devices: dict[SourceName, Device], all_sources: list[SourceName]) -> ComparisonEntry:
    present_in = list(devices.keys())
    missing_in = [s for s in all_sources if s not in devices]

    diffs: list[FieldDiff] = []
    hostnames = {s.value: d.hostname for s, d in devices.items()}
    if len(set(v.strip().lower() if v else v for v in hostnames.values())) > 1:
        diffs.append(FieldDiff(field="hostname", values=hostnames))

    for field in ("ip", "os"):
        values = {s.value: getattr(d, field) for s, d in devices.items()}
        present_values = [v for v in values.values() if v]
        if len(devices) > 1 and len(set(v.strip().lower() for v in present_values)) > 1:
            diffs.append(FieldDiff(field=field, values=values))

    if missing_in:
        status = MatchStatus.missing
    elif diffs:
        status = MatchStatus.field_mismatch
    else:
        status = MatchStatus.match

    hostname = next(iter(devices.values())).hostname if devices else key

    return ComparisonEntry(
        key=key,
        hostname=hostname,
        present_in=present_in,
        missing_in=missing_in,
        status=status,
        diffs=diffs,
        devices={s.value: d for s, d in devices.items()},
    )
