# EntityGuard

**Datenschutz-Schutzschicht für LLM-gestützte Anwendungen im Gesundheitswesen.**

EntityGuard sitzt zwischen dem Nutzer und dem Sprachmodell. Bevor eine Nachricht das LLM erreicht, erkennt und maskiert der Dienst automatisch personenbezogene und medizinische Daten — DSGVO- und HIPAA-konform, ohne Neustart bei Konfigurationsänderungen.

```
Eingabe:  "Patient Max Mustermann, geb. 15.03.1980, behandelt in der Charité."
Ausgabe:  "[NAME_1], geb. [DATUM/ZEIT_1], behandelt in der [ORGANISATION_1]."
```

**Stack:** FastAPI · Microsoft Presidio · spaCy (`de_core_news_lg`) · SQLite · Alembic · Docker

---

## Inhaltsverzeichnis

- [Schnellstart](#schnellstart)
- [Erkannte Entitäten](#erkannte-entitäten)
- [API](#api)
- [Admin-Interface](#admin-interface)
- [OpenWebUI-Integration](#openwebui-integration)
- [Docker](#docker)
- [Konfiguration](#konfiguration)
- [Transformer-Modelle (optionaler Qualitäts-Boost)](#transformer-modelle-optionaler-qualitäts-boost)
- [Architektur](#architektur)
- [Rechtliches & Compliance](#rechtliches--compliance)
- [Entwicklung](#entwicklung)
- [Fehlerbehebung](#fehlerbehebung)

---

## Schnellstart

### Voraussetzungen

- Python 3.13+
- [uv](https://github.com/astral-sh/uv)

### Lokale Installation

```bash
# 1. Abhängigkeiten installieren
uv sync

# 2. Deutsches spaCy-Modell herunterladen (~500 MB, einmalig)
uv run python -m spacy download de_core_news_lg

# 3. Schema und Standard-Daten über Alembic anlegen
uv run alembic upgrade head

# 4. Dienst starten
uv run python main.py
```

Der Dienst ist unter `http://localhost:9500` erreichbar.  
Der Admin-Benutzer `admin` / `admin` wird durch `uv run alembic upgrade head` angelegt.

### Erster Test

Zuerst im Admin-Interface unter **API-Schlüssel** einen Schlüssel erzeugen
(der Klartext wird nur einmal angezeigt) und ihn hier einsetzen:

```bash
curl -s -X POST http://localhost:9500/api/v1/sanitize \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eg_…" \
  -d '{"text": "Patient Max Mustermann, geb. 15.03.1980, behandelt in der Charité."}' \
  | python -m json.tool
```

Erwartete Antwort:
```json
{
  "sanitized_text": "[NAME_1], geb. [DATUM/ZEIT_1], behandelt in der [ORGANISATION_1].",
  "mapping": {
    "[NAME_1]": "Patient Max Mustermann",
    "[DATUM/ZEIT_1]": "15.03.1980",
    "[ORGANISATION_1]": "Charité"
  }
}
```

Das Anrede-Muster `anrede_name` fasst `Patient + Name` zusammen; die deutsche
spaCy-NER erkennt „Charité" als Organisation. Ohne Anrede bleibt der Name
isoliert (z. B. nur `Max Mustermann`).

---

## Erkannte Entitäten

| Entität | Beispiel | Platzhalter |
|---------|----------|-------------|
| `PERSON` | Max Mustermann, Frau Stolz, Dr. Schmidt | `[NAME]` |
| `LOCATION` | Berlin, Musterstraße 1 | `[ADRESSE/ORT]` |
| `ORGANIZATION` | Charité Berlin | `[ORGANISATION]` |
| `DATE_TIME` | 15.03.1980 | `[DATUM/ZEIT]` |
| `EMAIL_ADDRESS` | max@beispiel.de | `[EMAIL]` |
| `PHONE_NUMBER` | +49 30 123456, 0171/1234567 | `[TELEFON]` |
| `MEDICAL_CONTEXT` | AOK, Chefarzt, Fallnr. 48291 | `[MED_IDENTIFIKATOR]` |
| `IBAN_CODE` | DE89 3704 0044 0532 0130 00 | `[SENSITIV]` |

Wodurch eine Entität erkannt wird, zeigt das Admin-Interface pro Entität
(Spalte „Erkennung“): `Muster` (eigene Regexe), `spaCy`/`Presidio`
(Standard-Engines) und `Modell: …` (nur aktive Transformer). Entitäten ohne
Quelle werden als „nicht erkannt“ markiert.

**Deutschland-spezifische Erkennung (Custom Patterns):**

| Kategorie | Beispiele |
|-----------|-----------|
| Namen mit Anrede | Herr/Frau/Patient/Dr./Prof. + Name (`anrede_name`) |
| Krankenkassen | AOK, TK, Techniker Krankenkasse, Barmer, DAK, Hallesche, Debeka |
| Berufe im exponierten Kontext | Chefarzt, Bürgermeister, Landrat, Vorstand, Abgeordneter |
| Gewerkschaften | ver.di, IG Metall, GEW, Marburger Bund |
| Fallnummern | 5+ stellige Zahlen im medizinischen Kontext (Patient, Akte, Befund) |
| Datum | DD.MM.YYYY (`datum_generic`) |
| IBAN | deutsche IBAN (`iban_de`) |
| Telefonnummern | +49- und 0-Präfix, verschiedene Formate |

Alle Patterns und Entitäten sind über das Admin-Interface konfigurierbar.

---

## API

> **Authentifizierung:** Alle `/api/v1/*`-Endpunkte (außer `/health`) verlangen
> einen API-Schlüssel. Schlüssel werden im Admin-Interface unter
> **API-Schlüssel** erzeugt (Bezeichnung pro App, mehrere Schlüssel möglich).
> Der Klartext wird **nur einmal** beim Erzeugen angezeigt. Solange **kein
> aktiver Schlüssel** existiert, antwortet die API mit **HTTP 401**
> (Fail-Closed). Der Schlüssel wird als Header mitgeschickt:
>
> ```bash
> curl -H "Authorization: Bearer eg_…" …
> # alternativ:
> curl -H "X-API-Key: eg_…" …
> ```

### `POST /api/v1/sanitize`

Anonymisiert den übergebenen Text.

**Request:**
```json
{
  "text": "Der zu anonymisierende Text."
}
```

| Feld | Typ | Pflicht | Beschreibung |
|------|-----|---------|--------------|
| `text` | string | ja | Zu anonymisierender Text |

**Response:**
```json
{
  "sanitized_text": "Der anonymisierte Text.",
  "mapping": {
    "[NAME_1]": "Original-Wert des ersten erkannten NAME-Treffers"
  }
}
```

Jede maskierte Entität erhält einen eindeutigen, durchnummerierten Platzhalter (z.B. `[EMAIL_1]`, `[EMAIL_2]` bei zwei E-Mail-Adressen im selben Text). Das `mapping` bildet jeden Platzhalter auf seinen Originalwert ab und erlaubt so eine spätere De-Anonymisierung des Textes.

**Fehlerverhalten:** Ohne gültigen API-Schlüssel HTTP 401; bei einem internen Fehler gibt der Dienst HTTP 500 zurück und lässt den Text **nicht** unverarbeitet durch (Fail-Closed-Prinzip).

---

### `POST /api/v1/reload`

Lädt alle Patterns neu aus der Datenbank — ohne Neustart.

Nach Änderungen im Admin-Interface diesen Endpoint aufrufen, um die neuen Patterns sofort zu aktivieren.

```bash
curl -X POST http://localhost:9500/api/v1/reload \
  -H "Authorization: Bearer eg_…"
```

**Response:**
```json
{
  "success": true,
  "recognizers_count": 9,
  "message": "Successfully reloaded 9 recognizers from database"
}
```

`recognizers_count` ist die Anzahl der geladenen Presidio-Recognizer (ein
`PatternRecognizer` je Entität mit Mustern plus die Standard-Engines) und
damit ein grober Indikator, kein exakter Entitätszähler.

---

### `GET /health`

Health-Check Endpoint für Monitoring und Docker.

```bash
curl http://localhost:9500/health
# {"status": "Service is running"}
```

---

## Admin-Interface

Das Admin-Interface verwaltet Entitäten, ihre Muster und optional zuschaltbare KI-Modelle zur Laufzeit.

**URL:** `http://localhost:9500/admin/login`  
**Standard-Login:** `admin` / `admin` — **Passwort nach dem ersten Login ändern!**

### Was du damit tun kannst

- **Entitäten verwalten** — zentrale Einheit: Datentyp + Platzhalter, aktivieren/deaktivieren
- **Muster hinzufügen** — als Stichwörter (einfach) oder Regex (fortgeschritten), mit Score (0.0–1.0)
- **Kontextwörter** — Wörter, die den Erkennungs-Score boosten, wenn sie im Text in der Nähe stehen
- **Muster-Tester** — Regex testen, bevor sie aktiv werden
- **Modelle** — optionale Transformer-Modelle per Schalter zuschalten
- **Ausnahmeliste** — Werte, die grundsätzlich **nie** maskiert werden (z. B. ein Firmenname, der fälschlich als Person/Organisation erkannt wird)
- **API-Schlüssel** — Zugangsschlüssel für die JSON-API (pro App, mehrere möglich), an-/ausschaltbar, einmalige Klartext-Anzeige
- **Benutzer** — weitere Konten anlegen (nur Admins)
- **Audit-Log** — wer/wann/was geändert hat (nur Admins)
- **Tracing** — inhaltsfreie Anfrage-Metadaten (nur Admins)
- **Passwort ändern** — unter Profil

#### Rollen

Es gibt zwei Rollen:

| Rolle | Darf |
|-------|------|
| **Admin** | alles: konfigurieren, Benutzer verwalten, Audit/Tracing einsehen |
| **Viewer** | nur ansehen — keine Änderungen (der Server lehnt Mutationen mit 403 ab) |

Der per Migration angelegte `admin` ist **Admin**. Weitere Konten werden unter
**Benutzer** angelegt; Admins können die Rolle ändern, Passwörter zurücksetzen,
Konten deaktivieren/löschen. Der eigene Zugang und der letzte aktive Admin
können nicht entfernt oder herabgestuft werden.

#### Audit-Log

Das **Audit-Log** protokolliert Konfigurationsänderungen (Entitäten, Muster,
Kontextwörter, Ausnahmeliste, API-Schlüssel, Modelle, Benutzer) sowie Logins —
**auch fehlgeschlagene**. Es speichert nur *wer/wann/was*, **nie die
geänderten Werte**.

#### Tracing (inhaltsfrei)

Das **Tracing** protokolliert pro Anonymisierungs-Anfrage nur Metadaten:
Zeit, App/Key-Präfix, Eingabelänge, Anzahl und Typ der Maskierungen, Dauer und
Status. **Es werden bewusst keine Texte, Originalwerte oder das `mapping`
gespeichert.** Steuerung per Umgebungsvariable; Einträge werden nach
`TRACE_RETENTION_DAYS` Tagen beim Start automatisch gelöscht.

Für Tests gibt es unter `http://localhost:9500/admin/sanitize` eine
Testseite (nur für eingeloggte Nutzer): links Text eingeben oder Datei laden,
rechts erscheint live die anonymisierte Version (inkl. Hervorhebung der
Platzhalter, Hover zeigt den Originalwert). Die Seite nutzt die Admin-Session
statt eines API-Schlüssels — im Browser liegt also kein Schlüssel.

### Reload nach Änderungen

Nach dem Speichern im Admin-Interface muss der Analyzer-Cache neu geladen werden:

```bash
curl -X POST http://localhost:9500/api/v1/reload
```

Das Umschalten von Modellen unter **Modelle** löst den Reload automatisch aus.

### Neue Entität anlegen

1. Admin-Interface öffnen → **Entitäten** → **Entität erstellen**
2. Name und Platzhalter vergeben (z.B. `PATIENT_ID` / `[PATIENT_ID]`)
3. Auf der Detailseite **Muster hinzufügen** — Stichwörter (z.B. `AOK, TK, Barmer`) oder Regex (`\b\d{5,}\b`, Score `0.3`)
4. Optional: Kontextwörter, die den Score boosten (z.B. `patient`, `akte`, `fallnummer`)
5. **Muster testen** → Reload aufrufen

**Faustregel für Confidence-Scores:**

| Score | Bedeutung |
|-------|-----------|
| 0.9–1.0 | Sehr eindeutiges Pattern (Krankenkassen-Name, IBAN) |
| 0.7–0.9 | Eindeutiges Pattern, wenig Kontext nötig |
| 0.3–0.5 | Ambiges Pattern — Context Words zwingend erforderlich |

---

## OpenWebUI-Integration

EntityGuard lässt sich als Filter in OpenWebUI einbinden. Der Filter fängt jede Nutzer-Nachricht ab, schickt sie an EntityGuard und ersetzt den Originaltext durch die anonymisierte Version — bevor das LLM sie sieht.

Vollständige Anleitung inkl. Filter-Code, Konfiguration und Docker-Setup: **[docs/OpenWebUI.md](docs/OpenWebUI.md)**

**Kurzfassung:**

1. Filter-Code aus `docs/OpenWebUI.md` in OpenWebUI unter **Settings → Functions** einfügen
2. Als globalen Filter aktivieren
3. `api_url` auf den EntityGuard-Dienst setzen **und** `api_key` auf einen im Admin-Interface erzeugten Schlüssel:

| Szenario | `api_url` |
|----------|-----------|
| Lokal (kein Docker) | `http://localhost:9500/api/v1/sanitize` |
| Docker, gleiches Netzwerk | `http://entityguard:9500/api/v1/sanitize` |
| Docker, anderes Netzwerk | `http://host.docker.internal:9500/api/v1/sanitize` |

Optional kann der Filter die Platzhalter in der LLM-Antwort clientseitig wieder
durch die Originalwerte ersetzen (De-Anonymisierung über das `mapping`); das
LLM sieht die Klardaten dabei nie. Details und Code:
[docs/OpenWebUI.md](docs/OpenWebUI.md#antwort-de-anonymisierung-mit-dem-mapping).

---

## Docker

### Starten

```bash
docker-compose up -d
```

Das Dockerfile installiert das spaCy-Modell bereits beim Build — der Container ist beim Start sofort bereit.

### Health-Check

```bash
curl http://localhost:9500/health
```

### Logs anzeigen

```bash
docker-compose logs -f entityguard
```

### Datenbank persistieren

Das `docker-compose.yml` nutzt das benannte Volume `entityguard-data` (`/app/data`). Die SQLite-Datenbank und der HuggingFace-Modell-Cache bleiben bei `docker-compose down` erhalten. Beim Start führt der Container `alembic upgrade head` aus, ein Image-Update migriert also auch ein bestehendes Volume.

### Fertige Images (GHCR, amd64 + arm64)

```bash
docker pull ghcr.io/s2a-open-technologies/entityguard:latest       # torch Standard (CUDA-Wheels auf amd64)
docker pull ghcr.io/s2a-open-technologies/entityguard:latest-cpu   # torch CPU-only, deutlich kleiner
```

Versions-Tags: `X.Y.Z`, `X.Y`, `X` (jeweils auch mit Suffix `-cpu`); `edge` / `edge-cpu` folgen dem `master`-Branch. Lokal bauen: `docker build --build-arg TORCH_VARIANT=cpu .`

---

## Konfiguration

### Umgebungsvariablen

| Variable | Beschreibung | Default |
|----------|--------------|---------|
| `PYTHONUNBUFFERED` | Log-Ausgabe direkt in Container-Logs | `1` |
| `TRACE_ENABLED` | Inhaltsfreies Anfragen-Tracing an/aus (`true`/`false`) | `true` |
| `TRACE_RETENTION_DAYS` | Aufbewahrung der Trace-Einträge in Tagen | `7` |
| `TRACE_HMAC_SECRET` | Secret für den optionalen keyed Input-Hash (nur wenn gesetzt wird gehasht) | – |
| `BERT_NER_MODEL` | HuggingFace-Modell (nur relevant ohne DB, z. B. Benchmark-Script; muss in der Registry sein) | `fhswf/bert_de_ner` |
| `BERT_NER_DEVICE` | Device erzwingen (`cpu`, `cuda`, `cuda:0`), sonst Auto-Erkennung | automatisch |
| `BERT_NER_ENABLED` | Fallback ohne DB-Session (Benchmark-Script) | `false` |

### Transformer-Modelle (optionaler Qualitäts-Boost)

EntityGuard unterstützt mehrere Transformer-Modelle, die **parallel** zu
spaCy + Regex-Patterns laufen und je über einen An/Aus-Schalter auf der
Admin-Seite **Modelle** (`/admin/modelle`) verwaltet werden
(`backend/components/bert_recognizer.py`, `BERT_MODEL_REGISTRY`):

| Modell (Admin-UI) | HuggingFace | Stärke | CPU | GPU |
|---|---|---|---|---|
| `transformer_ner_fhswf` | `fhswf/bert_de_ner` (110M) | Freie Namen, Orte, **Organisationen** in Fließtext (65 % → 87 % Recall vs. spaCy allein) | ~77 ms | ~14 ms |
| `transformer_pii_openmed_small` | `OpenMed-PII-German-…-Small-44M` (44M) | Strukturiertes PII als Sicherheitsnetz über den Regex-Patterns: Adressen, Geburtsdatum, IBAN, E-Mail, Telefon | ~111 ms | ~18 ms |
| `transformer_pii_openmed_base` | `OpenMed-PII-German-…-Base-184M` (184M) | wie Small, genauer (F1 0.963) | ~167 ms | ~27 ms |
| `transformer_pii_openmed_large` | `OpenMed-PII-German-…-Large-434M` (434M) | genauste Variante (F1 0.976) | ~680 ms | ~45 ms |

Werte = Median über je 15 `process_text`-Aufrufe, 4 CPU-Kerne / RTX 3060;
erzeugt mit `uv run python scripts/benchmark_all_models.py` (läuft jedes
Modell als Subprozess, CPU + GPU, mit Warmup). Die beiden großen OpenMed-
Modelle sind im Admin-UI mit **„GPU empfohlen"** markiert: ohne CUDA sind
sie spürbar langsamer (Base ~3×, Large ~11× vs. GPU).

**Alle Modelle sind ab Werk deaktiviert** (Migrationen `010`/`011`/`012`),
da spaCy + Patterns die Kernentitäten mit ~6 ms abdecken. Zum Aktivieren:

1. Admin-UI → **Modelle** → gewünschtes Modell → Einschalten (greift sofort,
   kein Neustart und kein separater Reload nötig)

Mehrere Modelle gleichzeitig aktiv sind erlaubt (Latenzen addieren sich).
Beim ersten aktivierten Request lädt der Analyzer jedes Modell einmalig
(fhswf ~440 MB, OpenMed 44M ~180 MB, 184M ~730 MB, 434M ~1,7 GB); danach
bleiben sie für die Prozesslebensdauer im Speicher und überleben `/reload`.

Nicht gemappte Labels (z. B. SSN, AGE des OpenMed-Modells) werden verworfen.
Neue Entitätstypen lassen sich ergänzen: Entität im Admin-UI anlegen und das
Label in `BERT_MODEL_REGISTRY` nachtragen.

Docker-Deployments haben typischerweise keine GPU; dort laufen aktivierte
Modelle automatisch auf CPU - für die großen Varianten ist das nur mit
entsprechender Latenz tolerierbar.

### Analyzer-Parameter (`backend/components/cstm_analyzer.py`)

| Parameter | Beschreibung | Default |
|-----------|--------------|---------|
| `default_score_threshold` | Mindest-Confidence für Entity-Erkennung | `0.4` |
| `language` | Sprachcode für die Analyse | `de` |

---

## Architektur

```
main.py                          FastAPI App Factory, Uvicorn Port 9500
│
├── backend/views/anonymizer.py  Router: /api/v1/*
│   └── _analyzer                Gecachter CustomAnalyzer (Singleton)
│
├── backend/components/
│   └── cstm_analyzer.py         CustomAnalyzer (Presidio + spaCy)
│                                DatabasePatternProvider (DB → PatternRecognizer)
│
├── backend/database/
│   ├── models.py                EntityModel, PatternModel, ContextWordModel, DetectorModel, AdminUser
│   ├── crud.py                  CRUD-Operationen
│
├── backend/admin/               Admin-UI-Routen (Jinja2, Session-Auth)
│
├── frontend/                    Statische Assets & Templates
│   ├── static/                  CSS, JS
│   └── templates/               Jinja2-Templates (Admin-UI, Sanitize-Seite)
│
└── alembic/                     Datenbankmigrationen (inkl. Seed-Daten)
```

### Datenfluss

```
Nutzer-Nachricht
      │
      ▼
OpenWebUI inlet() Filter
      │
      ▼  POST /api/v1/sanitize
CustomAnalyzer.process_text()
      ├── analyzer.analyze()     → Entitäten erkennen (spaCy + Muster je Entität + optionale Modelle)
      └── anonymizer.anonymize() → Platzhalter einsetzen (aus DB)
      │
      ▼
Bereinigter Text → LLM
```

**Fail-Closed:** Jeder Fehler in der Pipeline gibt HTTP 500 zurück. Der unbereingte Text erreicht das LLM nie.

---

## Rechtliches & Compliance

EntityGuard ist eine **zustandslose Anonymisierungsschicht**: Es speichert
weder den analysierten Text noch das `mapping`. Für Betreiber und Audits:

- [`docs/data-mapping.md`](docs/data-mapping.md) — Datenfluss, Datenkategorien,
  Aufbewahrung (Ausgangspunkt für Art. 30 DSGVO).
- [`docs/pii.md`](docs/pii.md) — Maskierungs-Pipeline und Response-Contract.
- [`docs/audit-checklist-entityguard.md`](docs/audit-checklist-entityguard.md) —
  Selbstauskunft entlang typischer Audit-Prüfpunkte.
- [`SECURITY.md`](SECURITY.md) — Sicherheitsarchitektur, Art.-32-Maßnahmen,
  Deployment-Hinweise.
- [`DISCLAIMER.md`](DISCLAIMER.md) — Haftung und Einsatzhinweise
  (kein Medizinprodukt; automatische Erkennung ist nicht fehlerfrei).

Das Admin-UI bietet dafür ein **Audit-Log** (`/admin/audit`, Filter nach
Akteur/Aktion/Typ/Zeitraum + CSV-/JSON-Export) und ein inhaltsfreies
**Tracing** (`/admin/traces`).

---

## Entwicklung

```bash
# Abhängigkeiten installieren
uv sync

# Tests ausführen
uv run pytest

# Tests mit Output
uv run pytest -v

# Neue Datenbankmigration erstellen
uv run alembic revision --autogenerate -m "beschreibung"

# Migrationen anwenden
uv run alembic upgrade head
```

---

## Fehlerbehebung

**spaCy-Modell fehlt**
```
OSError: [E050] Can't find model 'de_core_news_lg'
```
```bash
uv run python -m spacy download de_core_news_lg
```

**Datenbank nicht initialisiert**
```
OperationalError: no such table: entities
```
```bash
uv run alembic upgrade head
```

**Neue Patterns werden nicht erkannt**  
Nach Änderungen im Admin-Interface den Analyzer-Cache neu laden:
```bash
curl -X POST http://localhost:9500/api/v1/reload -H "Authorization: Bearer eg_…"
```

**Container startet, aber kein Health-Check**  
Das spaCy-Modell wird beim Docker-Build eingebunden. Bei einem unvollständigen Build fehlt es. Neu bauen:
```bash
docker-compose build --no-cache
docker-compose up -d
```

**OpenWebUI blockiert alle Anfragen**  
EntityGuard verwendet Fail-Closed: wenn der Dienst nicht erreichbar ist, werden Anfragen blockiert. Dienst-Status prüfen:
```bash
curl http://localhost:9500/health
docker-compose logs entityguard
```
