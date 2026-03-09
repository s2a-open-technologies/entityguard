# Medical Chat Sanitizer (Guardrails)

Ein **FastAPI-basierter Dienst zur Anonymisierung von Patientendaten** gemäß **DSGVO** und **HIPAA**-Richtlinien. Der Dienst wird primär als Sicherheits-Layer für LLM-gestützte Chat-Systeme (z.B. OpenWebUI) eingesetzt, um sensible medizinische und personenbezogene Daten zu maskieren, bevor sie an das Sprachmodell übermittelt werden.

---

## Inhaltsverzeichnis

- [Funktionsweise](#funktionsweise)
- [Architektur](#architektur)
- [Erkannte Entitäten](#erkannte-entitäten)
- [Installation](#installation)
- [Nutzung](#nutzung)
- [API-Endpoints](#api-endpoints)
- [OpenWebUI-Integration](#openwebui-integration)
- [Docker](#docker)
- [Konfiguration](#konfiguration)

---

## Funktionsweise

Der Dienst nutzt Microsofts **Presidio**-Framework in Kombination mit **spaCy** (deutsches NLP-Modell), um sensible Informationen im Text zu identifizieren und durch Platzhalter zu ersetzen.

**Beispiel:**
```
Eingabe: "Patient Max Mustermann, geb. 15.03.1980, 
          wohnhaft in Berlin, wurde von Dr. Schmidt behandelt."

Ausgabe: "Patient [NAME], geb. [DATUM/ZEIT], 
          wohnhaft in [ADRESSE/ORT], wurde von [NAME] behandelt."
```

---

## Architektur

```
guardrails/
├── main.py                      # FastAPI Application Factory
├── src/
│   ├── components/
│   │   ├── cstm_analyzer.py     # Wrapper für Presidio Analyzer & Anonymizer
│   │   └── cstm_patterns.py     # Custom Pattern Recognizers (DE-spezifisch)
│   └── views/
│       └── anonymizer_view.py   # FastAPI Router mit /sanitize Endpoint
└── docs/
    └── OpenWebUI.md             # OpenWebUI Filter-Integration
```

### Komponenten

| Datei | Beschreibung |
|-------|--------------|
| `main.py` | Erstellt die FastAPI-App, registriert Router, startet Uvicorn auf Port 6000 |
| `src/components/cstm_analyzer.py` | Initialisiert Presidio Analyzer mit spaCy NLP-Engine (`de_core_news_lg`), definiert Anonymisierungs-Operatoren |
| `src/components/cstm_patterns.py` | Definiert benutzerdefinierte Regex-Patterns für deutsche Telefonnummern, E-Mails, Fallnummern, medizinische Kontexte (Krankenkassen, Berufe, Gewerkschaften) |
| `src/views/anonymizer_view.py` | Stellt den `/api/v1/guardrails/sanitize`-Endpoint bereit, unterstützt abteilungsspezifische Regelwerke |

---

## Erkannte Entitäten

Der Dienst erkennt und maskiert folgende Entitätstypen:

| Entität | Beispiel | Ersetzung |
|---------|----------|-----------|
| `PERSON` | Max Mustermann, Dr. Schmidt | `[NAME]` |
| `LOCATION` | Berlin, Musterstraße 1 | `[ADRESSE/ORT]` |
| `DATE_TIME` | 15.03.1980, 14:30 Uhr | `[DATUM/ZEIT]` |
| `EMAIL_ADDRESS` | max@example.com | `[EMAIL]` |
| `PHONE_NUMBER` | +49 30 123456, 0171/1234567 | `[TELEFON]` |
| `MEDICAL_CONTEXT` | Fallnummer 12345, AOK, Chefarzt | `[MED_IDENTIFIKATOR]` |
| `IBAN_CODE` | DE89 1234 5678 9012 3456 78 | `[SENSITIV]` |
| `FALLNUMMER` | Patientenakte 98765 | `[MED_IDENTIFIKATOR]` |

### Custom Patterns (Deutschland-spezifisch)

- **Krankenkassen**: AOK, TK, Techniker Krankenkasse, Barmer, DAK, Hallesche, Debeka
- **Berufe im exponierten Kontext**: Bürgermeister, Landrat, Vorstand, Abgeordneter, Chefarzt
- **Gewerkschaften**: ver.di, IG Metall, GEW, Marburger Bund
- **Fallnummern**: 5+ stellige Zahlen im medizinischen Kontext (Patient, Akte, Befund)
- **Geburtsdaten**: DD.MM.YYYY Format im medizinischen Kontext
- **Deutsche Telefonnummern**: +49 oder 0-Präfix mit verschiedenen Formatierungen

---

## Installation

### Voraussetzungen

- Python 3.13+
- [uv](https://github.com/astral-sh/uv) (empfohlen) oder pip

### Lokale Installation

```bash
# Repository klonen
git clone <repository-url>
cd guardrails

# Abhängigkeiten installieren (mit uv)
uv sync

# spaCy NLP-Modell herunterladen
uv run python -m spacy download de_core_news_lg

# Dienst starten
uv run python main.py
```

Der Server ist nun unter `http://localhost:6000` erreichbar.

---

## API-Endpoints

### `POST /api/v1/guardrails/sanitize`

Anonymisiert den übergebenen Text.

**Request Body:**
```json
{
  "text": "Patient Max Mustermann wurde in der Charité behandelt.",
  "department": "standard"
}
```

**Response:**
```json
{
  "sanitized_text": "Patient [NAME] wurde in [ADRESSE/ORT] behandelt.",
  "applied_department": "standard"
}
```

| Parameter | Typ | Beschreibung |
|-----------|-----|--------------|
| `text` | string | Der zu anonymisierende Text |
| `department` | string (optional) | Abteilungsspezifisches Regelwerk (default: "standard") |

### `GET /health`

Health-Check Endpoint.

**Response:**
```json
{
  "status": "Dienst läuft"
}
```

---

## OpenWebUI-Integration

Der Dienst kann als **Filter** in OpenWebUI integriert werden, um eingehende Nachrichten vor der Verarbeitung durch das LLM zu sanitieren.

Die Filter-Implementierung befindet sich in [`docs/OpenWebUI.md`](docs/OpenWebUI.md).

**Konfiguration in OpenWebUI:**

| Einstellung | Beschreibung |
|-------------|--------------|
| `api_url` | URL des Guardrails-Dienstes (z.B. `http://guardrails:6000/api/v1/guardrails/sanitize`) |
| `department_id` | Zu verwendendes Regelwerk (z.B. "standard", "psychiatrie", "cardio") |
| `timeout` | Timeout in Sekunden für den API-Aufruf (default: 5) |

Bei einem Fehler des Guardrails-Dienstes wird die Anfrage **blockiert** (Fail-Closed-Prinzip).

---

## Docker

### Dockerfile

Das Projekt enthält ein `Dockerfile`, das alle notwendigen Abhängigkeiten (inkl. spaCy NLP-Modell) installiert.

### docker-compose.yml

```yaml
version: '3.8'

services:
  guardrails:
    build: .
    ports:
      - "6000:6000"
    environment:
      - PYTHONUNBUFFERED=1
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    restart: unless-stopped
```

**Starten mit Docker Compose:**
```bash
docker-compose up -d
```

---

## Konfiguration

### Umgebungsvariablen

| Variable | Beschreibung | Default |
|----------|--------------|---------|
| `PYTHONUNBUFFERED` | Log-Ausgabe direkt in Container-Logs | `1` |

### Analyzer-Konfiguration

In `src/components/cstm_analyzer.py` können folgende Werte angepasst werden:

- `default_score_threshold`: Mindestkonfidenz für Entity-Erkennung (default: 0.4)
- `active_entities`: Liste der zu erkennenden Entitätstypen
- `operators`: Maskierungsregeln pro Entitätstyp

### Eigene Pattern hinzufügen

**Aktuell (statisch):**
Neue Regex-Patterns können in `src/components/cstm_patterns.py` im `MedicalPatternProvider` hinzugefügt werden. Anschließend ist ein **Neustart des Containers** erforderlich.

**Zukünftig (dynamisch via Web-UI):**
Es ist eine **Web-Oberfläche** in Planung, die es ermöglicht, Patterns und Regeln zur Laufzeit zu verwalten:

- ✅ Patterns dynamisch hinzufügen, bearbeiten und löschen
- ✅ Regelwerke pro Abteilung (z.B. `psychiatrie`, `cardio`) konfigurieren
- ✅ Änderungen werden **ohne Container-Neustart** übernommen
- ✅ Live-Vorschau der Pattern-Erkennung
- ✅ Export/Import von Regelwerk-Konfigurationen

Die Web-UI wird unter einem separaten Endpoint (z.B. `/admin`) erreichbar sein und optional aktiviert werden können.

---

## Lizenz

Dieses Projekt dient als Sicherheits-Layer für die Verarbeitung von Patientendaten und sollte gemäß den geltenden Datenschutzbestimmungen (DSGVO, HIPAA) eingesetzt werden.
