# InventCompare

Gleicht Server- und Netzwerkgeräte-Inventare zwischen mehreren Quellsystemen ab
und zeigt Abweichungen grafisch an. Aktuell angebunden: **Zabbix** (Monitoring,
JSON-RPC), **i-doit** (CMDB, JSON-RPC) und **GitLab** (REST API v4 – pro Server
ein eigenes Dokumentations-Projekt unter konfigurierten Gruppenpfaden). Weitere
Quellen können nach demselben Connector-Muster ergänzt werden.

## Features

- **Automatischer Abgleich** – periodischer Sync (Intervall einstellbar) plus manueller "Sync jetzt"-Button
- **Existenz-/Vollständigkeitsprüfung** – welches Gerät ist in welcher Quelle vorhanden bzw. fehlt
- **Feld-Abgleich** – IP-Adresse und Betriebssystem zwischen den Quellen auf Abweichungen prüfen
- **Matching** – primär über Hostname (Domain-Anteil optional abtrennbar), Fallback über IP-Adresse
- **Dashboard** – Verbindungsstatus, Erreichbarkeit und Gerätezahl je Quelle
- **Vergleichstabelle** – filterbar nach Status (übereinstimmend / Abweichung / fehlend) und Hostname
- **Graph-Ansicht** – Geräte als Knoten, farbcodiert nach Abgleichsstatus, verbunden mit den Quellsystemen
- **Konfiguration über Web-UI** – Sync-Intervall, aktive Quellen, Matching-Optionen, i-doit-Objekttypen, Zabbix-Hostgruppen
- **Zugangsdaten nur in `.env`** – Credentials aller Quellen liegen ausschließlich in der `.env` auf dem Docker-Host, nicht in der Web-Oberfläche oder im Repo

## Stack

| Komponente | Technologie |
|------------|-------------|
| Frontend | Vanilla HTML/JS + vis-network.js |
| Backend | FastAPI (Python 3.12), httpx |
| Speicher | JSON-Dateien (Settings + letzter Vergleichs-Snapshot) |
| Web-Server | nginx |
| Deployment | Docker Compose |

## Schnellstart

```bash
git clone https://github.com/kennerblick/inventcompare.git
cd inventcompare
cp .env.example .env
# .env anpassen: ZABBIX_URL/-TOKEN, IDOIT_URL/-API_KEY, GITLAB_URL/-TOKEN eintragen
docker compose up -d
```

Danach erreichbar unter: `http://<server-ip>:9091` (Port über `NGINX_PORT` in `.env` änderbar)

API-Dokumentation: `http://<server-ip>:9091/docs`

Beim ersten Aufruf ist noch kein Abgleich vorhanden – im Dashboard oben rechts
auf **"Sync jetzt"** klicken, um den ersten Sync anzustoßen.

## Konfiguration

### Zugangsdaten (`.env` auf dem Docker-Host)

Siehe `.env.example`. Wichtig: **`.env` nicht ins Git-Repo einchecken** (steht
in `.gitignore`). Nach Änderungen an `.env`: `docker compose up -d` erneut
ausführen, damit der Backend-Container die neuen Werte lädt.

- **Zabbix**: entweder `ZABBIX_API_TOKEN` (empfohlen, Administration -> API-Tokens)
  oder `ZABBIX_USER`/`ZABBIX_PASSWORD`.
- **i-doit**: `IDOIT_API_KEY` (Mandanten-Schlüssel) plus `IDOIT_USER`/`IDOIT_PASSWORD`
  eines Benutzers mit Leserechten. `IDOIT_URL` muss auf den JSON-RPC-Endpunkt
  zeigen, üblicherweise `https://<host>/src/jsonrpc.php`.
- **GitLab**: `GITLAB_API_TOKEN` (Personal- oder Group-Access-Token, Scope
  `read_api` genügt). `GITLAB_URL` ist die Basis-URL der Instanz (ohne `/api/v4`).

### Alles Weitere über die Web-Oberfläche (Einstellungen)

- Sync-Intervall (Minuten)
- Aktive Quellen (Zabbix/i-doit/GitLab einzeln deaktivierbar)
- Matching: Groß-/Kleinschreibung ignorieren, Domain vom Hostnamen trennen
- i-doit-Objekttypen, die als Server/Netzwerkgerät gelten (Default: `C__OBJTYPE__SERVER`,
  `C__OBJTYPE__NETWORK_DEVICE`, `C__OBJTYPE__VIRTUAL_SERVER`)
- i-doit: nur Objekte mit CMDB-Status "In Betrieb" (abschaltbar)
- Zabbix-Hostgruppen-Filter (leer = alle Hosts, inkl. Untergruppen "Parent/Child")
- GitLab-Gruppenpfade, unter denen je Server ein Projekt liegt (inkl. Untergruppen),
  z.B. `it-services/Hardware/Server`; archivierte Projekte standardmäßig ausgeschlossen

## Relevante API-Endpunkte

- `GET /api/health`
- `GET /api/sources` – Konfigurations-/Verbindungsstatus je Quelle
- `POST /api/sources/{name}/test` – Verbindungstest ohne vollen Sync
- `GET /api/comparison` – letzter Vergleichs-Snapshot
- `POST /api/comparison/sync` – Sync + Vergleich anstoßen
- `GET /api/settings`, `PUT /api/settings` – nicht-sensible Einstellungen

## Hinweise zu den Connectoren

- **Zabbix**: nutzt `host.get` inkl. Interfaces (IP, Erreichbarkeit) und
  Inventory-Feldern (`os`/`os_full`) – Host-Inventar muss in Zabbix gepflegt
  bzw. Inventory-Modus aktiviert sein, damit das Betriebssystem befüllt ist.
- **i-doit**: listet Objekte per `cmdb.objects.read` und liest je Objekt die
  Kategorien `C__CATG__IP` und `C__CATG__OS` nach. Je nach i-doit-Version oder
  individuellen Anpassungen können Attributnamen innerhalb dieser Kategorien
  abweichen – bei Bedarf in `backend/app/connectors/idoit.py` anpassen.
- **GitLab**: listet Projekte je konfiguriertem Gruppenpfad per
  `GET /groups/:id/projects?include_subgroups=true`. Liefert keine IP/OS-Daten,
  zählt also nur für Existenz-/Vollständigkeitsabgleich (ist für den Server ein
  Dokumentations-Projekt vorhanden). Der Projektname ist der primäre Match-Name,
  der Projekt-Pfad (falls abweichend) ein zusätzlicher Alias.

Neue Connectoren folgen dem Interface in `backend/app/connectors/base.py`.

## Entwicklung

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload
```

## Lizenz

MIT
