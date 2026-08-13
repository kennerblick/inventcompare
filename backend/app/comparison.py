"""Abgleich der Geräte aus mehreren Quellen.

Matching-Strategie (konfigurierbar über settings.matching):
1. Primär über normalisierten Hostnamen.
2. Für in nur einer Quelle gefundene Hostnamen: Versuch, das Gegenstück
   in der/den anderen Quelle(n) über die IP-Adresse zu finden.

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

    # Index je Quelle: normalisierter Hostname -> Device
    indexed: dict[SourceName, dict[str, Device]] = {}
    for source, devices in devices_by_source.items():
        idx: dict[str, Device] = {}
        for device in devices:
            key = _normalize_hostname(device.hostname, strip_domain, ignore_case)
            if key and key not in idx:
                idx[key] = device
        indexed[source] = idx

    sources = list(devices_by_source.keys())
    all_keys = set()
    for idx in indexed.values():
        all_keys.update(idx.keys())

    entries: list[ComparisonEntry] = []
    consumed: dict[SourceName, set[str]] = {s: set() for s in sources}

    for key in sorted(all_keys):
        devices: dict[SourceName, Device] = {}
        for source in sources:
            device = indexed[source].get(key)
            if device is not None:
                devices[source] = device
                consumed[source].add(key)
        entries.append(_build_entry(key, devices, sources))

    # Zweiter Durchlauf: verbliebene (nicht gematchte) Geräte über IP verknüpfen
    leftovers: dict[SourceName, dict[str, Device]] = {
        source: {k: d for k, d in idx.items() if k not in consumed[source]} for source, idx in indexed.items()
    }
    merged_keys: set[str] = set()
    ip_matched_entries: list[ComparisonEntry] = []

    leftover_list = [(source, key, device) for source, idx in leftovers.items() for key, device in idx.items()]
    for i, (source_a, key_a, device_a) in enumerate(leftover_list):
        if key_a in merged_keys or not device_a.ip:
            continue
        for source_b, key_b, device_b in leftover_list[i + 1 :]:
            if source_b == source_a or key_b in merged_keys:
                continue
            if key_a in merged_keys:
                break
            if device_b.ip and _normalize_ip(device_b.ip) == _normalize_ip(device_a.ip):
                combined = {source_a: device_a, source_b: device_b}
                ip_matched_entries.append(_build_entry(key_a, combined, sources))
                merged_keys.add(key_a)
                merged_keys.add(key_b)

    # Entries entfernen, die nun Teil eines IP-Matches sind, und stattdessen die kombinierten einfügen
    entries = [e for e in entries if e.key not in merged_keys]
    entries.extend(ip_matched_entries)
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
