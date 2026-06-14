# EntityGuard / Guardrails — Detaillierte technische und inhaltliche Dokumentation

Diese Datei beschreibt das Projekt **EntityGuard** (Arbeitsname im Repository: `guardrails`) so detailliert wie möglich. Sie richtet sich an Entwicklerinnen und Entwickler, DevOps-Teams, Datenschutzbeauftragte, Kliniken, Krankenkassen, Forschungseinrichtungen und alle, die die Anwendung betreiben, erweitern oder in eine OpenWebUI-/LLM-Landschaft integrieren möchten.

---

## Inhaltsverzeichnis

1. [Überblick: Was ist EntityGuard?](#1-überblick-was-ist-entityguard)
2. [Das Ziel der App](#2-das-ziel-der-app)
   - 2.1 [Primäres Ziel: Datenschutz-„Guardrail“ für LLM-Inputs](#21-primäres-ziel-datenschutz-guardrail-für-llm-inputs)
   - 2.2 [Sekundäres Ziel: Compliance ohne Deploy-Zwang](#22-sekundäres-ziel-compliance-ohne-deploy-zwang)
   - 2.3 [Zielgruppen](#23-zielgruppen)
3. [Das Ziel der App in Verbindung mit der AGPL](#3-das-ziel-der-app-in-verbindung-mit-der-agpl)
   - 3.1 [Warum AGPL?](#31-warum-agpl)
   - 3.2 [Was die AGPL in der Praxis bedeutet](#32-was-die-agpl-in-der-praxis-bedeutet)
   - 3.3 [Lizenztext in der Anwendung](#33-lizenztext-in-der-anwendung)
4. [Technischer Stack](#4-technischer-stack)
5. [Projektstruktur](#5-projektstruktur)
6. [Installation und Betrieb](#6-installation-und-betrieb)
   - 6.1 [Lokale Entwicklung](#61-lokale-entwicklung)
   - 6.2 [Docker & Docker Compose](#62-docker--docker-compose)
7. [Datenbank und Alembic-Migrationen](#7-datenbank-und-alembic-migrationen)
   - 7.1 [Migrationen im Detail](#71-migrationen-im-detail)
8. [Architektur und Datenfluss](#8-architektur-und-datenfluss)
   - 8.1 [Komponentendiagramm](#81-komponentendiagramm)
   - 8.2 [Presidio-Integration](#82-presidio-integration)
   - 8.3 [Fail-Closed-Verhalten](#83-fail-closed-verhalten)
9. [API-Endpunkte im Detail](#9-api-endpunkte-im-detail)
   - 9.1 [POST /api/v1/entityguard/sanitize](#91-post-apiv1entityguardsanitize)
   - 9.2 [POST /api/v1/entityguard/reload](#92-post-apiv1entityguardreload)
   - 9.3 [GET /health](#93-get-health)
10. [Codeschnipsel](#10-codeschnipsel)
    - 10.1 [FastAPI-App-Fabrik](#101-fastapi-app-fabrik)
    - 10.2 [CustomAnalyzer](#102-customanalyzer)
    - 10.3 [Pattern-Reload](#103-pattern-reload)
    - 10.4 [Sanitize-Endpoint](#104-sanitize-endpoint)
    - 10.5 [Admin-Auth](#105-admin-auth)
    - 10.6 [CRUD-Operationen](#106-crud-operationen)
    - 10.7 [Alembic-Seed-Migration](#107-alembic-seed-migration)
    - 10.8 [OpenWebUI-Filter](#108-openwebui-filter)
11. [Web-Oberfläche](#11-web-oberfläche)
    - 11.1 [Login](#111-login)
    - 11.2 [Dashboard](#112-dashboard)
    - 11.3 [Entities](#113-entities)
    - 11.4 [Recognizers](#114-recognizers)
    - 11.5 [Pattern-Detailseite mit Live-Preview](#115-pattern-detailseite-mit-live-preview)
    - 11.6 [Passwort ändern](#116-passwort-ändern)
    - 11.7 [Reload-Button](#117-reload-button)
12. [Nutzung der App](#12-nutzung-der-app)
    - 12.1 [Einfache API-Nutzung](#121-einfache-api-nutzung)
    - 12.2 [Erweiterung um eigene Patterns](#122-erweiterung-um-eigene-patterns)
    - 12.3 [OpenWebUI-Integration](#123-openwebui-integration)
    - 12.4 [Troubleshooting](#124-troubleshooting)
13. [Datenschutz- und Sicherheitshinweise](#13-datenschutz--und-sicherheitshinweise)
14. [Erweiterungsmöglichkeiten](#14-erweiterungsmöglichkeiten)
15. [Anhang: Vollständige Datei- und Code-Referenz](#15-anhang-vollständige-datei--und-code-referenz)

---

## 1. Überblick: Was ist EntityGuard?

**EntityGuard** ist ein schlanker, selbst gehosteter **FastAPI**-Dienst, der Texteingaben vor der Weitergabe an ein Large Language Model (LLM) automatisch auf personenbezogene und medizinische Daten scannt und diese durch anonymisierte Platzhalter ersetzt.

Beispiel:

```text
Eingabe:  "Patient Max Mustermann, geb. 15.03.1980, AOK-versichert, Fallnr. 48291"
Ausgabe:  "Patient [NAME], geb. [DATUM/ZEIT], [MED_IDENTIFIKATOR]-versichert, Fallnr. [MED_IDENTIFIKATOR]"
```

Die Anwendung ist explizit für den Einsatz im Gesundheitswesen konzipiert, wo DSGVO, HIPAA und andere Datenschutz- bzw. Patientenschutzvorgaben eine strenge Kontrolle von personenbezogenen Daten erfordern. Sie arbeitet als **Inline-Proxy** oder **Filter** und kann beispielsweise in OpenWebUI als sogenannter „Inlet-Filter“ eingebunden werden.

### Kern-Eigenschaften

- **Sprachfokus Deutsch**: Verwendet das spaCy-Modell `de_core_news_lg` für Named Entity Recognition (NER).
- **Microsoft Presidio**: Bietet anonymisierende Ersetzung und Confidence-Scores.
- **SQLite + Alembic**: Migrations-gesteuerte Datenbank, die Schema und Seed-Daten bereitstellt.
- **HTML-Admin-UI**: Ermöglicht das Editieren von Erkennern (Recognizers), Regex-Patterns, Context-Words und Entitäten über einen Browser.
- **Hot-Reload**: Konfigurationsänderungen können ohne Neustart über `POST /api/v1/entityguard/reload` oder einen UI-Button aktiviert werden.
- **Fail-Closed**: Bei jedem internen Fehler wird HTTP 500 zurückgegeben; unverarbeiteter Text gelangt nie an das LLM.

---

## 2. Das Ziel der App

### 2.1 Primäres Ziel: Datenschutz-„Guardrail“ für LLM-Inputs

EntityGuard ist ein sogenannter **Guardrail** (Leitplanke/Schutzschranke). Ein Guardrail ist eine Schicht zwischen Benutzer und KI, die sicherstellt, dass sensible Informationen das Sprachmodell nie im Klartext erreichen.

Bei LLM-Anwendungen im Gesundheitswesen ist dies besonders kritisch, weil:

1. **Patientendaten** (Namen, Geburtsdaten, Fallnummern, Diagnosen, Versicherungen) als besondere personenbezogene Daten gelten.
2. **Externe LLM-APIs** (z. B. OpenAI, Anthropic, Google) Daten für Training oder Logging verwenden könnten, auch wenn sie es nicht explizit tun.
3. **Prompt-Injection oder versehentliche Eingaben** sensible Inhalte in Chat-Interfaces freisetzen können.

EntityGuard minimiert dieses Risiko, indem es **vor** der LLM-Verarbeitung Ersetzungen vornimmt. Das LLM sieht nur Platzhalter wie `[NAME]`, `[DATUM/ZEIT]` oder `[MED_IDENTIFIKATOR]`.

### 2.2 Sekundäres Ziel: Compliance ohne Deploy-Zwang

Klassische PII-Anonymisierung ist oft hart kodiert. Wenn ein neuer Pattern-Typ benötigt wird, muss ein Entwickler den Code anpassen, testen und neu deployen. EntityGuard trennt **Regelwerk** (Patterns, Entities) vom **Code**.

Dank der Admin-Oberfläche und der Datenbank-gestützten Recognizer können Datenschutzbeauftragte, Medizincontroller oder Fachabteilungen neue Erkennungsregeln hinzufügen, ohne Python-Code zu berühren.

> **Hot-Reload**: Änderungen werden sofort nach `POST /api/v1/entityguard/reload` aktiv – ohne Container-Neustart, ohne Downtime.

### 2.3 Zielgruppen

| Zielgruppe | Nutzen |
|------------|--------|
| Kliniken & Praxen | Patientendaten werden vor LLM-Verarbeitung maskiert |
| Krankenkassen | Vermeidung von Vertrags- und Sozialdaten-Leaks |
| Forschungseinrichtungen | Anonymisierung von Freitext in Studien |
| DevOps-Teams | Leichtgewichtiger Container, einfach skalierbar |
| Datenschutzbeauftragte | Konfiguration über Web-UI, Nachvollziehbarkeit durch DB-Logs/Migrationen |
| OpenWebUI-Betreiber | Nahtlose Filter-Integration |

---

## 3. Das Ziel der App in Verbindung mit der AGPL

### 3.1 Warum AGPL?

EntityGuard steht unter der **GNU Affero General Public License v3 (AGPL-3.0)**. Diese Lizenz wurde gewählt, weil die Anwendung in drei Bereichen sozial und technisch besonders relevant ist:

1. **Netzwerkdienst als Software**: EntityGuard läuft als Server. Bei einer gewöhnlichen GPL könnte ein Betreiber Änderungen am Code vornehmen, ihn nicht veröffentlichen und den Dienst dennoch öffentlich oder intern anbieten. Die AGPL schließt diese Lücke.
2. **Datenschutz und öffentliches Interesse**: Sicherheits- und Anonymisierungssoftware profitiert von öffentlicher Prüfung. Je mehr Augen den Code sehen, desto eher werden Fehler in Erkennungsmustern oder der Anonymisierungslogik gefunden.
3. **Gemeinwohl im Gesundheitswesen**: Kliniken und Behörden sollen nicht von proprietären „Black-Box“-Diensten abhängig sein. AGPL erlaubt jedem, die Software kostenlos zu nutzen, zu verbessern und weiterzugeben.

### 3.2 Was die AGPL in der Praxis bedeutet

Für Nutzerinnen und Nutzer von EntityGuard hat die AGPL folgende Konsequenzen:

- **Freie Nutzung**: Die Software kann kostenlos installiert, betrieben und angepasst werden.
- **Quellcode offen**: Der Quellcode liegt offen; jeder kann ihn prüfen.
- **„Network Use is Distribution“**: Werden modifizierte Versionen von EntityGuard über ein Netzwerk bereitgestellt (auch nur intern im Krankenhausnetz für andere Abteilungen), muss der Quellcode der Modifikationen den Nutzern zur Verfügung gestellt werden.
- **Kopierecht**: Der ursprüngliche Copyright-Hinweis (hier: Christopher Abanilla, 2026) muss erhalten bleiben.
- **Keine Garantie**: Wie bei GPL üblich wird die Software „as is“ ohne Gewährleistung bereitgestellt.

### 3.3 Lizenztext in der Anwendung

Jede Python-Datei enthält einen Lizenzkopf. Beispiel aus `main.py`:

```python
"""
EntityGuard - FastAPI Application Entry Point.
Copyright (C) 2026  Christopher Abanilla

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""
```

Dieser Header ist in **allen** Python-Dateien des Projekts vorhanden und stellt sicher, dass jede einzelne Datei – auch bei isolierter Weitergabe – die Lizenzinformation trägt.

---

## 4. Technischer Stack

| Komponente | Zweck |
|------------|-------|
| **FastAPI** | Web-Framework für API und Admin-UI |
| **Uvicorn** | ASGI-Server |
| **Pydantic** | Request/Response-Validierung |
| **Microsoft Presidio** | PII-Analyse und -Anonymisierung |
| **spaCy `de_core_news_lg`** | Deutsche Named Entity Recognition (PERSON, LOCATION, ORG, DATE_TIME) |
| **SQLAlchemy 2.0** | ORM für SQLite |
| **Alembic** | Datenbankmigrationen |
| **Jinja2** | HTML-Templates für Admin-UI |
| **bcrypt / passlib** | Passwort-Hashing |
| **python-multipart** | Form-Uploads in der Admin-UI |
| **uv** | Python-Paketmanager und Lockfile |
| **Docker** | Containerisierung |

---

## 5. Projektstruktur

```
guardrails/
├── AGENTS.md                      # Kurzanleitung für Coding-Agenten
├── README.md                      # Benutzerdokumentation
├── guardrails.md                  # Diese Datei
├── Dockerfile                     # Container-Build
├── docker-compose.yml             # Compose-Setup
├── main.py                        # FastAPI-App-Fabrik + Uvicorn-Start
├── pyproject.toml                 # uv-Projektdefinition
├── uv.lock                        # Gesperrte Abhängigkeiten
├── alembic/
│   ├── alembic.ini                # Alembic-Konfiguration
│   ├── env.py                     # Migration Runtime
│   └── versions/
│       ├── 001_initial.py         # Schema-Initialisierung
│       ├── 002_seed_initial_recognizers.py
│       ├── 003_add_builtin_recognizers.py
│       ├── 004_seed_default_admin_user.py
│       └── 005_seed_remaining_entities.py
├── docs/
│   └── OpenWebUI.md               # OpenWebUI-Filter-Anleitung
└── src/
    ├── __init__.py
    ├── components/
    │   ├── __init__.py
    │   └── cstm_analyzer.py       # CustomAnalyzer (Presidio + DB)
    ├── database/
    │   ├── __init__.py
    │   ├── crud.py                  # CRUD-Operationen
    │   ├── database.py              # SessionLocal, Engine
    │   └── models.py                # SQLAlchemy-Modelle
    ├── admin/
    │   ├── __init__.py
    │   ├── auth.py                  # Session-Auth
    │   ├── dependencies.py          # Template-Kontext
    │   └── routes.py                # Admin-Routen
    ├── views/
    │   ├── __init__.py
    │   └── anonymizer.py            # API-Routen /api/v1/entityguard/*
    ├── static/
    │   ├── css/admin.css            # Admin-Styles
    │   └── js/admin.js              # Admin-JavaScript
    └── templates/
        ├── base.html                # Basis-Layout
        ├── login.html
        ├── dashboard.html
        ├── profile/password.html
        ├── entities/
        │   ├── list.html
        │   ├── create.html
        │   └── edit.html
        ├── patterns/edit.html
        └── recognizers/
            ├── list.html
            ├── create.html
            ├── edit.html
            └── view.html
```

---

## 6. Installation und Betrieb

### 6.1 Lokale Entwicklung

Voraussetzungen:

- Python 3.13+
- `uv` installiert

```bash
# 1. Abhängigkeiten installieren
uv sync

# 2. Deutsches spaCy-Modell herunterladen (~500 MB)
uv run python -m spacy download de_core_news_lg

# 3. Schema + Seed-Daten über Alembic anlegen
uv run alembic upgrade head

# 4. Dienst starten
uv run python main.py
```

Der Dienst lauscht auf Port **9500** (`http://localhost:9500`).

### 6.2 Docker & Docker Compose

```bash
# Container bauen und starten
docker-compose up -d

# Logs einsehen
docker-compose logs -f entityguard

# Health-Check
curl http://localhost:9500/health
```

Das Dockerfile installiert das spaCy-Modell bereits während des Builds, sodass der Container beim Start sofort einsatzbereit ist. Das `data/`-Verzeichnis wird als Volume eingebunden, damit die SQLite-Datenbank über `docker-compose down` hinaus erhalten bleibt.

---

## 7. Datenbank und Alembic-Migrationen

Die Datenbank ist eine SQLite-Datei unter `data/entityguard.db`. Sie ist die **einzige** Quelle für:

- Schema
- Standard-Entities
- Standard-Recognizers
- Standard-Patterns
- Context-Words
- Den Admin-Benutzer

**Wichtig**: `main.py` startet den Dienst **nicht** mit automatischem DB-Seeding. Vor dem ersten Start muss immer `uv run alembic upgrade head` ausgeführt werden.

### 7.1 Migrationen im Detail

| Migration | Zweck |
|-----------|-------|
| `001_initial.py` | Erstellt die Tabellen `recognizers`, `patterns`, `context_words`, `admin_users`, `entities` |
| `002_seed_initial_recognizers.py` | Fügt Start-Entities (PERSON, LOCATION, DATE_TIME, EMAIL_ADDRESS, PHONE_NUMBER, MEDICAL_CONTEXT, IBAN_CODE) und erste Recognizers mit Patterns ein |
| `003_add_builtin_recognizers.py` | Fügt Spalte `is_builtin` hinzu; markiert Presidio-eigene Erkenner als built-in |
| `004_seed_default_admin_user.py` | Legt idempotent den Benutzer `admin` / `admin` an |
| `005_seed_remaining_entities.py` | Ergänzt z. B. die Entity `FALLNUMMER` |

---

## 8. Architektur und Datenfluss

### 8.1 Komponentendiagramm

```
Nutzer / OpenWebUI
       │
       ▼
POST /api/v1/entityguard/sanitize
       │
       ▼
┌──────────────────────────────────────────────────┐
│  FastAPI Router: src/views/anonymizer.py         │
│  - Validierung mit Pydantic                      │
│  - Caching in _analyzer_registry                 │
└──────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────┐
│  CustomAnalyzer: src/components/cstm_analyzer.py   │
│  - Presidio AnalyzerEngine                       │
│  - Presidio AnonymizerEngine                     │
│  - spaCy NER (de_core_news_lg)                   │
│  - DB-PatternProvider (Custom Patterns)          │
└──────────────────────────────────────────────────┘
       │
       ▼
SQLite DB: data/entityguard.db
       │
       ├── recognizers     (aktive Erkenner)
       ├── patterns        (Regex + Score)
       ├── context_words   (Kontext-Boost)
       ├── entities        (Platzhalter + Aktivflag)
       └── admin_users     (Login)
```

### 8.2 Presidio-Integration

EntityGuard nutzt Microsoft Presidio in einer stark angepassten Form:

- Es **entfernt fast alle Presidio-eigenen Built-in-Recognizers** (z. B. für Kreditkarten, IBAN, E-Mail, Telefon).
- Es **behält nur den spaCy-NLP-Erkenner** bei (`spacy_nlp`), um Personen, Orte und Datumsangaben via deutschem Modell zu finden.
- Alle weiteren Patterns (E-Mail, Telefon, Fallnummern, Krankenkassen, Gewerkschaften, exponierte Berufe) werden **ausschließlich aus der Datenbank** geladen.

Dieses Design garantiert, dass das Verhalten der Anwendung vollständig über die Datenbank steuerbar ist.

### 8.3 Fail-Closed-Verhalten

In `src/views/anonymizer.py`:

```python
except Exception as e:
    logger.error(f"Error in guardrail routing: {e}")
    raise HTTPException(
        status_code=500,
        detail="Security abort: Data sanitization failed"
    )
```

Wenn also das spaCy-Modell fehlt, die Datenbank leer ist, ein Regex fehlerhaft ist oder die Presidio-Engine abstürzt, wird der Text **nicht** einfach durchgereicht. Stattdessen erhält der Aufrufer HTTP 500. In OpenWebUI führt das dazu, dass die Anfrage blockiert wird.

---

## 9. API-Endpunkte im Detail

### 9.1 POST /api/v1/entityguard/sanitize

Anonymisiert beliebigen Text.

**Request-Body:**

```json
{
  "text": "Patient Max Mustermann, geb. 15.03.1980, AOK-versichert, Fallnr. 48291",
  "department": "standard"
}
```

**Response:**

```json
{
  "sanitized_text": "Patient [NAME], geb. [DATUM/ZEIT], [MED_IDENTIFIKATOR]-versichert, Fallnr. [MED_IDENTIFIKATOR]",
  "applied_department": "standard"
}
```

**Fehlerfall (Fail-Closed):**

```json
HTTP/1.1 500 Internal Server Error
{
  "detail": "Security abort: Data sanitization failed"
}
```

### 9.2 POST /api/v1/entityguard/reload

Löscht den Analyzer-Cache und lädt alle Recognizer/Patterns/Entities neu aus der Datenbank. Wird nach Änderungen in der Admin-UI benötigt.

**Response:**

```json
{
  "success": true,
  "recognizers_count": 4,
  "message": "Successfully reloaded 4 recognizers from database"
}
```

### 9.3 GET /health

Einfacher Health-Check für Docker und Monitoring.

**Response:**

```json
{
  "status": "Service is running"
}
```

---

## 10. Codeschnipsel

### 10.1 FastAPI-App-Fabrik

`main.py`:

```python
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from src.admin import admin_router, get_current_user
from src.views import entityguard_router

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("EntityGuard starting up...")
    yield
    logger.info("Shutting down...")


def create_app():
    app = FastAPI(
        title="EntityGuard",
        description="Security layer for processing patient data according to GDPR & HIPAA",
        version="1.0.0",
        lifespan=lifespan
    )

    static_dir = Path(__file__).parent / "src" / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(entityguard_router)
    app.include_router(admin_router)

    @app.get("/health")
    async def health():
        return {"status": "Service is running"}

    @app.get("/")
    async def root_redirect(request: Request):
        if get_current_user(request):
            return RedirectResponse(url="/admin/dashboard", status_code=302)
        return RedirectResponse(url="/admin/login", status_code=302)

    return app


if __name__ == "__main__":
    uvicorn.run(create_app, host="0.0.0.0", port=9500)
```

### 10.2 CustomAnalyzer

`src/components/cstm_analyzer.py`:

```python
from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpEngineProvider
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from sqlalchemy.orm import Session

from src.database.crud import get_entities, get_recognizers
from src.database.models import RecognizerModel

nlp_configuration = {
    "nlp_engine_name": "spacy",
    "models" : [{
        "lang_code": "de",
        "model_name": "de_core_news_lg"
    }]
}


class DatabasePatternProvider:
    @staticmethod
    def get_recognizers_from_db(db: Session):
        recognizers = []
        db_recognizers = get_recognizers(db, active_only=True)

        for db_rec in db_recognizers:
            if db_rec.is_builtin:
                continue

            patterns = []
            for db_pattern in db_rec.patterns:
                try:
                    pattern = Pattern(
                        name=db_pattern.name,
                        regex=db_pattern.regex,
                        score=db_pattern.score
                    )
                    patterns.append(pattern)
                except Exception as e:
                    logger.warning(f"Invalid pattern '{db_pattern.name}': {e}")
                    continue

            context_words = [cw.word for cw in db_rec.context_words]

            recognizer = PatternRecognizer(
                supported_entity=db_rec.supported_entity,
                patterns=patterns,
                context=context_words if context_words else [],
                supported_language=db_rec.supported_language
            )
            recognizers.append(recognizer)

        return recognizers


class CustomAnalyzer:
    def __init__(self, language: str = "de", db = None):
        self.language = language
        self.anonymizer = AnonymizerEngine()
        self._db = db

        nlp_provider = NlpEngineProvider(nlp_configuration=nlp_configuration)
        nlp_engine = nlp_provider.create_engine()

        self.analyzer = AnalyzerEngine(
            nlp_engine=nlp_engine,
            default_score_threshold=0.4
        )
        self._remove_builtin_recognizers()

        recognizers = self._load_recognizers(db)
        for recognizer in recognizers:
            self.analyzer.registry.add_recognizer(recognizer=recognizer)

    def _remove_builtin_recognizers(self):
        recognizer_names = [r.name for r in self.analyzer.registry.recognizers if hasattr(r, 'name')]
        keep_recognizers = ['spacy_nlp', 'PatternRecognizer', 'Pattern', 'PatternRecognizerAdapter']
        for name in recognizer_names:
            if name not in keep_recognizers:
                try:
                    self.analyzer.registry.remove_recognizer(name)
                except Exception as e:
                    logger.warning(f"Could not remove recognizer '{name}': {e}")

    def _load_recognizers(self, db):
        if db:
            try:
                return DatabasePatternProvider.get_recognizers_from_db(db)
            except Exception as e:
                logger.warning(f"Error loading from database: {e}")
        return []

    def process_text(self, text: str, db=None) -> str:
        if not text.strip():
            return ""

        db_session = db or self._db
        entity_placeholders = {}
        active_entities = []

        if db_session:
            db_entities = get_entities(db_session, active_only=True)
            for entity in db_entities:
                entity_placeholders[entity.name] = entity.placeholder
                active_entities.append(entity.name)

        results = self.analyzer.analyze(
            text=text,
            language=self.language,
            entities=active_entities if active_entities else None
        )

        operators = {}
        for entity_name, placeholder in entity_placeholders.items():
            operators[entity_name] = OperatorConfig("replace", {"new_value": placeholder})
        operators["DEFAULT"] = OperatorConfig("replace", {"new_value": "[SENSITIV]"})

        anonymized_results = self.anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=operators
        )

        return anonymized_results.text
```

### 10.3 Pattern-Reload

`src/views/anonymizer.py`:

```python
_analyzer_registry: dict[str, CustomAnalyzer] = {}


@entityguard_router.post("/reload", response_model=ReloadResponse)
async def reload_patterns():
    try:
        _analyzer_registry.clear()

        db = SessionLocal()
        try:
            analyzer = CustomAnalyzer(language="de", db=db)
            recognizers_list = list(analyzer.analyzer.registry.recognizers)
            custom_count = max(0, len(recognizers_list) - 1)
            _analyzer_registry["standard"] = analyzer
            return ReloadResponse(
                success=True,
                recognizers_count=custom_count,
                message=f"Successfully reloaded {custom_count} recognizers from database"
            )
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Error reloading patterns: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reload patterns: {str(e)}")
```

### 10.4 Sanitize-Endpoint

`src/views/anonymizer.py`:

```python
class SanitizeRequest(BaseModel):
    text: str
    department: Optional[str] = "standard"


class SanitizeResponse(BaseModel):
    sanitized_text: str
    applied_department: str


@entityguard_router.post("/sanitize", response_model=SanitizeResponse)
async def sanitize(request: SanitizeRequest):
    try:
        department = request.department or "standard"
        analyzer = _get_or_create_analyzer(department)
        result_text = analyzer.process_text(request.text)

        return SanitizeResponse(
            sanitized_text=result_text,
            applied_department=department
        )
    except Exception as e:
        logger.error(f"Error in guardrail routing: {e}")
        raise HTTPException(
            status_code=500,
            detail="Security abort: Data sanitization failed"
        )
```

### 10.5 Admin-Auth

`src/admin/auth.py`:

```python
import secrets
import time
from datetime import datetime, timedelta
from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from src.database import SessionLocal
from src.database.crud import authenticate_admin_user, get_admin_user

_sessions: dict[str, dict] = {}
SESSION_COOKIE_NAME = "admin_session"
SESSION_EXPIRY_HOURS = 8


def create_session(user_id: int) -> str:
    session_id = secrets.token_urlsafe(32)
    expires_at = time.time() + (SESSION_EXPIRY_HOURS * 3600)
    _sessions[session_id] = {"user_id": user_id, "expires_at": expires_at}
    return session_id


def validate_session(session_id: str):
    session = _sessions.get(session_id)
    if not session:
        return None
    if time.time() > session["expires_at"]:
        del _sessions[session_id]
        return None
    return session["user_id"]


def get_current_user(request: Request):
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        return None
    user_id = validate_session(session_id)
    if not user_id:
        return None
    with SessionLocal() as db:
        user = get_admin_user(db, user_id)
        if not user or not user.is_active:
            return None
        return {"id": user.id, "username": user.username}


def require_auth(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/admin/login"}
        )
    return user
```

### 10.6 CRUD-Operationen

`src/database/crud.py`:

```python
from src.database.models import AdminUser, ContextWordModel, EntityModel, PatternModel, RecognizerModel


def get_recognizer(db: Session, recognizer_id: int):
    return db.query(RecognizerModel).filter(RecognizerModel.id == recognizer_id).first()


def get_recognizer_by_name(db: Session, name: str):
    return db.query(RecognizerModel).filter(RecognizerModel.name == name).first()


def get_recognizers(db: Session, active_only: bool = False):
    query = db.query(RecognizerModel)
    if active_only:
        query = query.filter(RecognizerModel.is_active == True)
    return query.all()


def create_recognizer(db: Session, name, supported_entity, supported_language="de", is_active=True):
    recognizer = RecognizerModel(
        name=name,
        supported_entity=supported_entity,
        supported_language=supported_language,
        is_active=is_active
    )
    db.add(recognizer)
    db.commit()
    db.refresh(recognizer)
    return recognizer


def create_pattern(db: Session, name, regex, score, recognizer_id):
    pattern = PatternModel(
        name=name,
        regex=regex,
        score=score,
        recognizer_id=recognizer_id
    )
    db.add(pattern)
    db.commit()
    db.refresh(pattern)
    return pattern


def create_context_word(db: Session, word, recognizer_id):
    context_word = ContextWordModel(word=word, recognizer_id=recognizer_id)
    db.add(context_word)
    db.commit()
    db.refresh(context_word)
    return context_word


def create_entity(db: Session, name, placeholder, description=None, is_active=True):
    entity = EntityModel(
        name=name,
        placeholder=placeholder,
        description=description,
        is_active=is_active
    )
    db.add(entity)
    db.commit()
    db.refresh(entity)
    return entity


def update_admin_password(db: Session, user_id, new_password):
    user = get_admin_user(db, user_id)
    if not user:
        return None
    user.password_hash = bcrypt.hashpw(
        new_password.encode('utf-8'), bcrypt.gensalt()
    ).decode('utf-8')
    user.last_password_change = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user
```

### 10.7 Alembic-Seed-Migration

`alembic/versions/002_seed_initial_recognizers.py` (Auszug):

```python
def upgrade():
    entities = [
        ('PERSON', '[NAME]', 'Personennamen'),
        ('LOCATION', '[ADRESSE/ORT]', 'Orte und Adressen'),
        ('DATE_TIME', '[DATUM/ZEIT]', 'Datums- und Zeitangaben'),
        ('EMAIL_ADDRESS', '[EMAIL]', 'E-Mail-Adressen'),
        ('PHONE_NUMBER', '[TELEFON]', 'Telefonnummern'),
        ('MEDICAL_CONTEXT', '[MED_IDENTIFIKATOR]', 'Medizinische Kontexte'),
        ('IBAN_CODE', '[SENSITIV]', 'IBAN-Codes'),
    ]

    for name, placeholder, description in entities:
        op.execute(f"""
            INSERT INTO entities (name, placeholder, description, is_active, created_at, updated_at)
            VALUES ('{name}', '{placeholder}', '{description}', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (name) DO UPDATE SET placeholder = '{placeholder}', is_active = 1, updated_at = CURRENT_TIMESTAMP
        """)

    recognizers = [
        ("medizinische_kontexte", "MEDICAL_CONTEXT", "de", 1),
        ("telefonnummern_de", "PHONE_NUMBER", "de", 1),
        ("email_adressen", "EMAIL_ADDRESS", "de", 1),
        ("fallnummern_und_daten", "MEDICAL_CONTEXT", "de", 1),
    ]

    for name, entity, lang, is_active in recognizers:
        op.execute(f"""
            INSERT INTO recognizers (name, supported_entity, supported_language, is_active, created_at, updated_at)
            VALUES ('{name}', '{entity}', '{lang}', {is_active}, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        """)
```

### 10.8 OpenWebUI-Filter

`docs/OpenWebUI.md`:

```python
import requests
import logging
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Filter:
    class Valves(BaseModel):
        api_url: str = Field(
            default="http://localhost:9500/api/v1/entityguard/sanitize",
            description="EntityGuard API URL"
        )
        department_id: str = Field(default="standard")
        timeout: int = Field(default=5)

    def __init__(self):
        self.valves = self.Valves()

    def inlet(self, body, __user__=None):
        messages = body.get("messages", [])
        if not messages:
            return body

        last_message = messages[-1]
        if last_message.get("role") != "user":
            return body

        user_text = last_message.get("content", "")
        payload = {"text": user_text, "department": self.valves.department_id}

        try:
            response = requests.post(
                self.valves.api_url,
                json=payload,
                timeout=self.valves.timeout
            )
            response.raise_for_status()
            data = response.json()
            sanitized_text = data.get("sanitized_text")
            if sanitized_text is None:
                raise ValueError("Received invalid response")
            body['messages'][-1]['content'] = sanitized_text
            return body
        except Exception as e:
            error_msg = f"Security check failed: {str(e)}"
            logger.error(error_msg)
            raise Exception(f"Privacy stop: {error_msg}")
```

---

## 11. Web-Oberfläche

Die Admin-Oberfläche ist eine klassische Server-Side-Rendered HTML-Anwendung auf Basis von Jinja2. Sie verwendet ein Sidebar-Layout, ein eigenes CSS (`src/static/css/admin.css`) und minimales JavaScript (`src/static/js/admin.js`).

### 11.1 Login

- URL: `http://localhost:9500/admin/login`
- Standard-Zugangsdaten: `admin` / `admin`
- Session-Cookie `admin_session`, 8 Stunden gültig, `httponly`, `samesite=lax`
- Nach erfolgreichem Login Redirect auf `/admin/dashboard`

### 11.2 Dashboard

- Statistiken: Anzahl Recognizer, aktive Recognizer, Gesamtzahl Patterns
- Tabelle der letzten fünf Recognizers mit Status und Pattern-Anzahl
- Quick-Actions: „New Recognizer“, „Manage Patterns“

### 11.3 Entities

- Liste aller Entitäten mit Name, Platzhalter, Beschreibung, Status
- Anlegen neuer Entitäten: Name (z. B. `INSURANCE_ID`), Platzhalter (z. B. `[VERSICHERUNGSNR]`), Beschreibung
- Editieren / Löschen / Aktivieren / Deaktivieren

> **Wichtig**: Nur aktive Entitäten werden an Presidio übergeben. Deaktivierte Entitäten werden nicht erkannt.

### 11.4 Recognizers

- Übersicht aller Erkenner mit Name, Entity, Sprache, Status, Patterns, Context-Words
- Neuer Recognizer: Name, `supported_entity` (muss einer Entity entsprechen), Sprache, Aktiv-Flag
- Jeder Recognizer kann beliebig viele Patterns und Context-Words enthalten

### 11.5 Pattern-Detailseite mit Live-Preview

Die Detailseite eines Recognizers zeigt:

- Metadaten (Entity, Sprache, Status, Erstellungszeit)
- Inline-Formular zum Hinzufügen neuer Regex-Patterns mit Name, Regex, Score
- Tabelle aller Patterns mit Editieren/Löschen
- Inline-Formular zum Hinzufügen von Context-Words
- Tags-Darstellung der Context-Words
- **Pattern-Preview**: Textarea + Regex-Feld; per Button werden Matches über `/admin/preview` getestet

### 11.6 Passwort ändern

- Menüpunkt oben in der Sidebar: `Change Password`
- Eingabe: aktuelles Passwort, neues Passwort (mind. 8 Zeichen), Bestätigung
- Erfolgsmeldung oder Validierungsfehler werden inline angezeigt

### 11.7 Reload-Button

Die Oberfläche enthält einen Button, der `POST /api/v1/entityguard/reload` aufruft. Er ist essenziell, denn sonst bleiben neu gespeicherte Patterns im laufenden Analyzer-Cache inaktiv.

---

## 12. Nutzung der App

### 12.1 Einfache API-Nutzung

```bash
# Dienst starten
uv run python main.py

# Health-Check
curl http://localhost:9500/health

# Text anonymisieren
curl -s -X POST http://localhost:9500/api/v1/entityguard/sanitize \
  -H "Content-Type: application/json" \
  -d '{"text": "Patient Max Mustermann, geb. 15.03.1980, AOK-versichert, Fallnr. 48291"}' \
  | python -m json.tool
```

Erwartete Antwort:

```json
{
  "sanitized_text": "Patient [NAME], geb. [DATUM/ZEIT], [MED_IDENTIFIKATOR]-versichert, Fallnr. [MED_IDENTIFIKATOR]",
  "applied_department": "standard"
}
```

### 12.2 Erweiterung um eigene Patterns

1. Im Browser `http://localhost:9500/admin` öffnen und mit `admin` / `admin` einloggen.
2. Passwort ändern (empfohlen).
3. Auf **Recognizers** → **Create Recognizer** klicken.
4. Name: `versicherungsnummer_de`, supported entity: `MEDICAL_CONTEXT`.
5. Speichern, zur Detailseite navigieren.
6. Pattern hinzufügen:
   - Name: `versicherungsnummer_de`
   - Regex: `\b\d{9,12}\b`
   - Score: `0.3`
7. Context-Words hinzufügen: `versicherung`, `versichert`, `kasse`, `kosten`, `versichertennummer`.
8. Auf **Reload** klicken.
9. Test:

```bash
curl -s -X POST http://localhost:9500/api/v1/entityguard/sanitize \
  -H "Content-Type: application/json" \
  -d '{"text": "Versichertennummer 1234567890"}'
```

### 12.3 OpenWebUI-Integration

1. In OpenWebUI unter **Settings → Functions** den Filter-Code aus `docs/OpenWebUI.md` hinzufügen.
2. Als globalen Filter aktivieren.
3. `api_url` je nach Netzwerkumgebung setzen:
   - Lokal: `http://localhost:9500/api/v1/entityguard/sanitize`
   - Docker (gleiches Netzwerk): `http://entityguard:9500/api/v1/entityguard/sanitize`
   - Docker (anderes Netzwerk): `http://host.docker.internal:9500/api/v1/entityguard/sanitize`
4. `department_id` auf `standard` lassen (oder ein zukünftiges Abteilungs-Regelwerk).

### 12.4 Troubleshooting

| Symptom | Ursache | Lösung |
|---------|---------|--------|
| `OSError: Can't find model 'de_core_news_lg'` | spaCy-Modell fehlt | `uv run python -m spacy download de_core_news_lg` |
| `OperationalError: no such table: recognizers` | DB nicht migriert | `uv run alembic upgrade head` |
| Neue Patterns werden nicht erkannt | Analyzer-Cache veraltet | `POST /api/v1/entityguard/reload` oder UI-Reload |
| Container antwortet nicht auf Health-Check | Build unvollständig | `docker-compose build --no-cache && docker-compose up -d` |
| OpenWebUI blockiert alle Anfragen | EntityGuard unerreichbar | Dienst-Logs prüfen, `api_url` korrigieren |

---

## 13. Datenschutz- und Sicherheitshinweise

- **Standardpasswort**: Direkt nach erstem Login auf `admin` / `admin` ändern.
- **Session-Store**: Sessions liegen aktuell im Arbeitsspeicher (einfacher Single-User-Betrieb). Bei horizontaler Skalierung ist ein zentraler Session-Store erforderlich.
- **Regex-Eingaben**: Der Server validiert Regex per `re.compile` vor dem Speichern.
- **SQL-Injection**: Alle DB-Zugriffe laufen über SQLAlchemy ORM; keine string-basierten Queries in der App selbst (Alembic-Migrationen nutzen Raw-SQL für Seeds).
- **Fail-Closed**: Produktive OpenWebUI-Integrationen sollten das Timeout nicht zu hoch setzen, aber auch nicht so niedrig, dass Timeout-Fehler zu viele Blockaden erzeugen.
- **AGPL-Compliance**: Wer modifizierte Versionen über Netzwerke bereitstellt, muss den Quellcode der Modifikationen zur Verfügung stellen.

---

## 14. Erweiterungsmöglichkeiten

- **Weitere Abteilungen (Departments)**: Aktuell ist nur `standard` implementiert. Weitere Abteilungen erfordern neue Analyzer-Instanzen in `_analyzer_registry` und können unterschiedliche Score-Thresholds oder Recognizer-Sets verwenden.
- **Redaction statt Replace**: Neben `replace` könnte Presidio `redact` (Entfernen) oder `hash` (Hashing) unterstützen.
- **Audit-Log**: Speichern jedes Sanitize-Requests (ohne Klartext!) zur Compliance-Dokumentation.
- **Multi-Language**: Weitere spaCy-Modelle für andere Sprachen laden.
- **Tests**: Derzeit keine Tests vorhanden; pytest ist bereits als Dev-Dependency konfiguriert.
- **API-Key-Authentifizierung**: Aktuell ist der `/api/v1/entityguard/*`-Namespace ungeschützt; für produktiven Einsatz sollte ein API-Key oder OAuth ergänzt werden.

---

## 15. Anhang: Vollständige Datei- und Code-Referenz

### Wichtige Dateien im Überblick

| Datei | Funktion |
|-------|----------|
| `main.py` | FastAPI-Factory, Uvicorn, Health-Check, Root-Redirect |
| `src/views/anonymizer.py` | API-Routen `/api/v1/entityguard/*`, Analyzer-Cache |
| `src/components/cstm_analyzer.py` | Presidio + spaCy + DB-Recognizer Logik |
| `src/admin/routes.py` | Alle Admin-HTML-Routen und Form-Handler |
| `src/admin/auth.py` | Session-basierte Authentifizierung |
| `src/database/models.py` | SQLAlchemy-Modelle |
| `src/database/crud.py` | CRUD-Funktionen |
| `src/templates/base.html` | Basis-Layout der Admin-UI |
| `src/static/js/admin.js` | Pattern-Preview, Alerts, Checkbox-Handling |
| `alembic/versions/001_initial.py` | Schema |
| `alembic/versions/002_seed_initial_recognizers.py` | Seed-Data |
| `alembic/versions/004_seed_default_admin_user.py` | Default-Login |
| `docs/OpenWebUI.md` | Integrationsanleitung und Filter-Code |

### Erkannte Entitäten (Default)

| Entity | Platzhalter | Beispiel |
|--------|-------------|----------|
| `PERSON` | `[NAME]` | Max Mustermann, Dr. Schmidt |
| `LOCATION` | `[ADRESSE/ORT]` | Berlin, Charité |
| `DATE_TIME` | `[DATUM/ZEIT]` | 15.03.1980 |
| `EMAIL_ADDRESS` | `[EMAIL]` | max@beispiel.de |
| `PHONE_NUMBER` | `[TELEFON]` | +49 30 123456 |
| `MEDICAL_CONTEXT` | `[MED_IDENTIFIKATOR]` | AOK, Fallnr. 48291 |
| `IBAN_CODE` | `[SENSITIV]` | DE89 3704 0044 ... |
| `FALLNUMMER` | `[FALLNUMMER]` | 48291 |

### Deutschland-spezifische Patterns (Default)

- Krankenkassen: AOK, TK, Techniker Krankenkasse, Barmer, DAK, Hallesche, Debeka
- Gewerkschaften: ver.di, IG Metall, GEW, Marburger Bund
- Exponierte Berufe: Bürgermeister, Landrat, Vorstand, Abgeordneter, Chefarzt
- Fallnummern: 5+ stellige Zahlen im medizinischen Kontext
- Geburtsdaten: DD.MM.YYYY-Format
- Telefonnummern: +49- und 0-Präfixe

---

*Dokumentation erstellt für EntityGuard / guardrails. Alle Quellcode-Ausschnitte stammen aus dem Repository und stehen unter AGPL-3.0. Copyright (C) 2026 Christopher Abanilla.*
