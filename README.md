# EntityGuard

**Datenschutz-Schutzschicht für LLM-gestützte Anwendungen im Gesundheitswesen.**

EntityGuard sitzt zwischen dem Nutzer und dem Sprachmodell. Bevor eine Nachricht das LLM erreicht, erkennt und maskiert der Dienst automatisch personenbezogene und medizinische Daten — DSGVO- und HIPAA-konform, ohne Neustart bei Konfigurationsänderungen.

```
Eingabe:  "Patient Max Mustermann, geb. 15.03.1980, AOK-versichert, Fallnr. 48291"
Ausgabe:  "Patient [NAME], geb. [DATUM/ZEIT], [MED_IDENTIFIKATOR]-versichert, Fallnr. [MED_IDENTIFIKATOR]"
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
- [Architektur](#architektur)
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

```bash
curl -s -X POST http://localhost:9500/api/v1/entityguard/sanitize \
  -H "Content-Type: application/json" \
  -d '{"text": "Patient Max Mustermann, geb. 15.03.1980, behandelt in der Charité."}' \
  | python -m json.tool
```

Erwartete Antwort:
```json
{
  "sanitized_text": "Patient [NAME], geb. [DATUM/ZEIT], behandelt in [ADRESSE/ORT].",
  "applied_department": "standard"
}
```

---

## Erkannte Entitäten

| Entität | Beispiel | Platzhalter |
|---------|----------|-------------|
| `PERSON` | Max Mustermann, Dr. Schmidt | `[NAME]` |
| `LOCATION` | Berlin, Musterstraße 1 | `[ADRESSE/ORT]` |
| `DATE_TIME` | 15.03.1980, 14:30 Uhr | `[DATUM/ZEIT]` |
| `EMAIL_ADDRESS` | max@beispiel.de | `[EMAIL]` |
| `PHONE_NUMBER` | +49 30 123456, 0171/1234567 | `[TELEFON]` |
| `MEDICAL_CONTEXT` | AOK, Chefarzt, Fallnr. 48291 | `[MED_IDENTIFIKATOR]` |
| `IBAN_CODE` | DE89 3704 0044 0532 0130 00 | `[SENSITIV]` |

**Deutschland-spezifische Erkennung (Custom Patterns):**

| Kategorie | Beispiele |
|-----------|-----------|
| Krankenkassen | AOK, TK, Techniker Krankenkasse, Barmer, DAK, Hallesche, Debeka |
| Berufe im exponierten Kontext | Chefarzt, Bürgermeister, Landrat, Vorstand, Abgeordneter |
| Gewerkschaften | ver.di, IG Metall, GEW, Marburger Bund |
| Fallnummern | 5+ stellige Zahlen im medizinischen Kontext (Patient, Akte, Befund) |
| Geburtsdaten | DD.MM.YYYY-Format mit medizinischen Kontextwörtern |
| Telefonnummern | +49- und 0-Präfix, verschiedene Formate |

Alle Patterns und Entitäten sind über das Admin-Interface konfigurierbar.

---

## API

### `POST /api/v1/entityguard/sanitize`

Anonymisiert den übergebenen Text.

**Request:**
```json
{
  "text": "Der zu anonymisierende Text.",
  "department": "standard"
}
```

| Feld | Typ | Pflicht | Beschreibung |
|------|-----|---------|--------------|
| `text` | string | ja | Zu anonymisierender Text |
| `department` | string | nein | Regelwerk (default: `standard`) |

**Response:**
```json
{
  "sanitized_text": "Der anonymisierte Text.",
  "applied_department": "standard"
}
```

**Fehlerverhalten:** Bei einem internen Fehler gibt der Dienst HTTP 500 zurück und lässt den Text **nicht** unverarbeitet durch (Fail-Closed-Prinzip).

---

### `POST /api/v1/entityguard/reload`

Lädt alle Patterns neu aus der Datenbank — ohne Neustart.

Nach Änderungen im Admin-Interface diesen Endpoint aufrufen, um die neuen Patterns sofort zu aktivieren.

```bash
curl -X POST http://localhost:9500/api/v1/entityguard/reload
```

**Response:**
```json
{
  "success": true,
  "recognizers_count": 4,
  "message": "Successfully reloaded 4 recognizers from database"
}
```

---

### `GET /health`

Health-Check Endpoint für Monitoring und Docker.

```bash
curl http://localhost:9500/health
# {"status": "Service is running"}
```

---

## Admin-Interface

Das Admin-Interface ermöglicht die Verwaltung von Pattern Recognizern zur Laufzeit.

**URL:** `http://localhost:9500/admin/login`  
**Standard-Login:** `admin` / `admin` — **Passwort nach dem ersten Login ändern!**

### Was du damit tun kannst

- **Recognizer verwalten** — erstellen, bearbeiten, aktivieren/deaktivieren
- **Patterns hinzufügen** — Regex mit Confidence-Score (0.0–1.0)
- **Context Words** — Wörter, die den Erkennungs-Score boosten, wenn sie im Text in der Nähe stehen
- **Live-Preview** — Regex testen bevor er aktiv wird
- **Passwort ändern** — unter Profil

### Pattern-Reload nach Änderungen

Nach dem Speichern im Admin-Interface muss der Analyzer-Cache neu geladen werden:

```bash
curl -X POST http://localhost:9500/api/v1/entityguard/reload
```

Alternativ: Browser → `http://localhost:9500/admin` → Reload-Button.

### Neuen Recognizer anlegen

1. Admin-Interface öffnen → **Recognizers** → **Neu**
2. Name und Entitätstyp vergeben (z.B. `MEDICAL_CONTEXT`)
3. Regex-Pattern mit Score hinzufügen (Beispiel: `\b\d{5,}\b` mit Score `0.3`)
4. Optional: Context Words, die den Score boosten (z.B. `patient`, `akte`, `fallnummer`)
5. Speichern → Reload aufrufen

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
3. `api_url` auf den EntityGuard-Dienst setzen:

| Szenario | `api_url` |
|----------|-----------|
| Lokal (kein Docker) | `http://localhost:9500/api/v1/entityguard/sanitize` |
| Docker, gleiches Netzwerk | `http://entityguard:9500/api/v1/entityguard/sanitize` |
| Docker, anderes Netzwerk | `http://host.docker.internal:9500/api/v1/entityguard/sanitize` |

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

Das `docker-compose.yml` bindet das `data/`-Verzeichnis als Volume ein. Die SQLite-Datenbank (`data/entityguard.db`) bleibt bei `docker-compose down` erhalten.

---

## Konfiguration

### Umgebungsvariablen

| Variable | Beschreibung | Default |
|----------|--------------|---------|
| `PYTHONUNBUFFERED` | Log-Ausgabe direkt in Container-Logs | `1` |

### Analyzer-Parameter (`src/components/cstm_analyzer.py`)

| Parameter | Beschreibung | Default |
|-----------|--------------|---------|
| `default_score_threshold` | Mindest-Confidence für Entity-Erkennung | `0.4` |
| `language` | Sprachcode für die Analyse | `de` |

### Abteilungsspezifische Regelwerke

Der `department`-Parameter im API-Request wählt ein Regelwerk aus. Aktuell ist nur `standard` implementiert. Um ein neues Regelwerk hinzuzufügen, muss in `src/views/anonymizer.py` ein neuer Analyzer in `_analyzer_registry` registriert werden.

---

## Architektur

```
main.py                          FastAPI App Factory, Uvicorn Port 9500
│
├── src/views/anonymizer.py      Router: /api/v1/entityguard/*
│   └── _analyzer_registry       Department → CustomAnalyzer Cache
│
├── src/components/
│   └── cstm_analyzer.py         CustomAnalyzer (Presidio + spaCy)
│                                DatabasePatternProvider (DB → PatternRecognizer)
│
├── src/database/
│   ├── models.py                RecognizerModel, PatternModel, EntityModel, AdminUser
│   ├── crud.py                  CRUD-Operationen
│
├── src/admin/                   Admin-UI (Jinja2, Session-Auth)
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
      ▼  POST /api/v1/entityguard/sanitize
CustomAnalyzer.process_text()
      ├── analyzer.analyze()     → Entitäten erkennen (spaCy + custom Patterns)
      └── anonymizer.anonymize() → Platzhalter einsetzen (aus DB)
      │
      ▼
Bereinigter Text → LLM
```

**Fail-Closed:** Jeder Fehler in der Pipeline gibt HTTP 500 zurück. Der unbereingte Text erreicht das LLM nie.

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
OperationalError: no such table: recognizers
```
```bash
uv run alembic upgrade head
```

**Neue Patterns werden nicht erkannt**  
Nach Änderungen im Admin-Interface den Analyzer-Cache neu laden:
```bash
curl -X POST http://localhost:9500/api/v1/entityguard/reload
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
