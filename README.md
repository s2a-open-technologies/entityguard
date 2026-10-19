# EntityGuard

**Datenschutz-Schutzschicht für LLM-gestützte Anwendungen im Gesundheitswesen.**

EntityGuard sitzt zwischen dem Nutzer und dem Sprachmodell. Bevor eine Nachricht das LLM erreicht, erkennt und maskiert der Dienst automatisch personenbezogene und medizinische Daten — DSGVO- und HIPAA-konform, ohne Neustart bei Konfigurationsänderungen.

```
Eingabe:  "Patient Max Mustermann, geb. 15.03.1980, behandelt in der Charité."
Ausgabe:  "[NAME_1], geb. [DATUM/ZEIT_1], behandelt in der [ORGANISATION_1]."
```

Bilder (Screenshots, Scans) werden optional per OCR gelesen, durch dieselbe
Erkennung geschickt und anschließend im Bild geschwärzt. Standard ist die
komplette OCR-Zeile eines Treffers; die Bildverarbeitung lässt sich im Admin
unter **Bild-OCR** oder per `ENTITYGUARD_OCR_*` konfigurieren.

**Stack:** FastAPI · Microsoft Presidio · spaCy (`de_core_news_lg`) · Tesseract/RapidOCR · SQLite · Alembic · Docker

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
> (Fail-Closed). Für Headless-Betrieb (z. B. Docker ohne Zugriff aufs
> Admin-UI) lässt sich zusätzlich ein Schlüssel per Umgebungsvariable
> `ENTITYGUARD_API_KEY` bzw. `ENTITYGUARD_API_KEY_FILE` vorgeben (siehe
> [Umgebungsvariablen](#umgebungsvariablen)). Der Schlüssel wird als Header mitgeschickt:
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
| `reuse_placeholders` | boolean | nein (Standard `false`) | `true`: Derselbe Wert (gleicher Text, gleiche Entität) bekommt im ganzen Text **denselben** Platzhalter, das `mapping` hat dann einen Eintrag je Wert. Sinnvoll, wenn mehrere Nachrichten eines Gesprächs als ein Text geschickt werden |

**Response:**
```json
{
  "sanitized_text": "Der anonymisierte Text.",
  "mapping": {
    "[NAME_1]": "Original-Wert des ersten erkannten NAME-Treffers"
  }
}
```

Jede maskierte Entität erhält einen eindeutigen, durchnummerierten Platzhalter (z.B. `[EMAIL_1]`, `[EMAIL_2]` bei zwei E-Mail-Adressen im selben Text). Das `mapping` bildet jeden Platzhalter auf seinen Originalwert ab und erlaubt so eine spätere De-Anonymisierung des Textes. Mit `reuse_placeholders: true` teilen sich identische Werte einen Platzhalter.

**Hinweise für große Texte:** Der Text außerhalb der Treffer bleibt Zeichen für Zeichen unverändert (Zeilenumbrüche, Leerzeichen, Trennmarken). Die Analyse läuft im Threadpool, andere Anfragen und `/health` werden dadurch nicht blockiert. Trennmarken ohne Buchstaben (z. B. `=====#1=====`) überstehen die Erkennung, Buchstabenmarken wie `=====MSG-1=====` können von der spaCy-NER als Entität erkannt werden.

**Fehlerverhalten:** Ohne gültigen API-Schlüssel HTTP 401; bei einem internen Fehler gibt der Dienst HTTP 500 zurück und lässt den Text **nicht** unverarbeitet durch (Fail-Closed-Prinzip).

---

### `POST /api/v1/sanitize/image`

Liest Text aus einem Bild per OCR, maskiert erkannte Entitäten und liefert ein
redigiertes PNG zurück. Das Bild wird nur im Speicher verarbeitet und **nie**
gespeichert. Bei einem Fehler wird das Originalbild nicht zurückgegeben.

**Request:**
```json
{
  "image_base64": "data:image/png;base64,iVBORw0KGgo...",
  "reuse_placeholders": true
}
```

| Feld | Typ | Pflicht | Beschreibung |
|------|-----|---------|--------------|
| `image_base64` | string | ja | Base64 oder Data-URI (`data:image/png;base64,...`); PNG, JPEG oder WebP |
| `reuse_placeholders` | boolean | nein (Standard `true`) | Gleicher Wert = gleicher Platzhalter im OCR-Text |

**Response:**
```json
{
  "sanitized_image_base64": "iVBORw0KGgo...",
  "sanitized_text": "Patient [NAME_1] aus [ADRESSE/ORT_1]",
  "ocr_text": "Patient Max Mustermann aus Berlin",
  "mapping": {"[NAME_1]": "Max Mustermann", "[ADRESSE/ORT_1]": "Berlin"},
  "ocr_engine": "tesseract",
  "ocr_device": "cpu",
  "ocr_confidence": 0.91,
  "latency_ms": 180.5,
  "image_width": 1200,
  "image_height": 800,
  "redactions": [{"box": [10, 20, 210, 50], "entity_types": ["PERSON"], "texts": ["Max Mustermann"]}],
  "entities": [{"type": "PERSON", "text": "Max Mustermann", "score": 0.99, "box": [10, 20, 210, 50]}],
  "warnings": []
}
```

`redactions` und `entities` dienen der Admin-Vorschau. `sanitized_image_base64`
ist ein PNG ohne Metadaten. Die Standard-Schwärzung `line` überdeckt die
komplette OCR-Zeile eines Treffers; `entity` schwärzt nur die erkannten Wörter,
`all_text` jeden erkannten Text. Bei `all_text` ist `sanitized_text` der
unveränderte OCR-Text (es gibt keine Entitäts-Platzhalter); maßgeblich ist das
redigierte Bild. OCR erfasst nur gedruckten Text – keine Handschrift, Gesichter
oder Logos.

**Fehlerverhalten:** HTTP 400/413/415 bei ungültigem, zu großem oder nicht
unterstütztem Bild; HTTP 404 wenn die Bildverarbeitung deaktiviert ist; HTTP
500 bei OCR-/Verifikationsfehlern (Fail-Closed).

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
- **Bild-OCR** — Tesseract/RapidOCR, Gerät, Schwärzungsmodus und Limits einstellen; Umgebungsvariablen überschreiben die Werte
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
Testseite (nur für eingeloggte Nutzer) mit zwei Modi:

- **Text:** links Text eingeben oder Datei laden, rechts erscheint live die
  anonymisierte Version (inkl. Hervorhebung der Platzhalter, Hover zeigt den
  Originalwert).
- **Bild:** links das Original mit roten Markierungen der geschwärzten
  Bereiche, rechts das redigierte PNG, darunter der maskierte OCR-Text,
  Engine/Gerät/Konfidenz und die Anzahl der Masken.

Die Seite nutzt die Admin-Session statt eines API-Schlüssels — im Browser
liegt also kein Schlüssel.

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

EntityGuard lässt sich als Filter in OpenWebUI einbinden. Der Filter fängt jede Nutzer-Nachricht ab, schickt sie an EntityGuard und ersetzt den Originaltext durch die anonymisierte Version — bevor das LLM sie sieht. Der fertige Filter behandelt auch Bilder.

Vollständige Anleitung inkl. Filter-Code, Konfiguration und Docker-Setup: **[docs/OpenWebUI.md](docs/OpenWebUI.md)**

**Kurzfassung:**

1. Filter aus [`integrations/openwebui/entityguard_filter.py`](integrations/openwebui/entityguard_filter.py) in OpenWebUI unter **Settings → Functions** einfügen (Kurzanleitung: [`integrations/openwebui/README.md`](integrations/openwebui/README.md))
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

Für Bilder zusätzlich `image_api_url` auf den Bild-Endpunkt setzen (z. B.
`http://entityguard:9500/api/v1/sanitize/image`) und `image_mode` wählen:
`block` (Default, fail-closed) oder `redact` (OCR + Schwärzung).

---

## Docker

### Starten

```bash
docker-compose up -d
```

Das Dockerfile installiert das spaCy-Modell sowie Tesseract inklusive der
Sprachpakete `deu` und `eng` bereits beim Build — der Container ist beim Start
sofort bereit. RapidOCR ist im Image enthalten; für RapidOCR auf einer
CUDA-GPU mit `--build-arg OCR_VARIANT=gpu` bauen (installiert
`onnxruntime-gpu` statt `onnxruntime`).

### Headless (ohne Admin-UI)

Soll der Container ohne Zugriff aufs Admin-UI laufen, lassen sich API-Schlüssel,
Admin-Passwort, Transformer-Modell und Bild-OCR per Umgebung vorgeben:

```bash
export ENTITYGUARD_API_KEY=$(openssl rand -hex 32)
export ENTITYGUARD_ADMIN_PASSWORD=$(openssl rand -base64 24)
docker run -d -p 9500:9500 \
  -e ENTITYGUARD_API_KEY -e ENTITYGUARD_ADMIN_PASSWORD \
  -e ENTITYGUARD_MODELS=openmed_small \
  -e ENTITYGUARD_OCR_ENGINE=auto \
  -e ENTITYGUARD_OCR_DEVICE=auto \
  -e ENTITYGUARD_OCR_REDACTION=line \
  -v entityguard-data:/app/data \
  ghcr.io/s2a-open-technologies/entityguard:latest-cpu
```

In `docker-compose.yml` die auskommentierten Zeilen aktivieren (oder die `_FILE`-Varianten
mit Docker Secrets nutzen).

- **`ENTITYGUARD_API_KEY`** gilt zusätzlich zu den im Admin-UI erzeugten Schlüsseln.
- **`ENTITYGUARD_ADMIN_PASSWORD`** legt beim Start das Konto `admin` (bzw.
  `ENTITYGUARD_ADMIN_USERNAME`) als aktiven Admin mit diesem Passwort an oder setzt es zurück –
  damit ist das Standard-Passwort `admin` sofort weg. Die Umgebung ist maßgeblich: Ein im UI
  geändertes Passwort wird beim nächsten Neustart wieder überschrieben.
- **`ENTITYGUARD_MODELS`** schaltet beim Start genau die genannten Modelle ein und alle anderen
  aus (`fhswf`, `openmed_small`, `openmed_base`, `openmed_large` oder der volle Registry-Name,
  mehrere komma-getrennt; `none` = alle aus). Schalter im UI wirken bis zum nächsten Neustart.
- **Ohne Internetverbindung:** Transformer-Modelle werden beim ersten Einsatz von HuggingFace in
  `/app/data/hf` (Volume) geladen. Für einen Offline-Container das Modell einmal mit
  Internetzugang laden (oder den HF-Cache ins Volume kopieren) und danach `HF_HUB_OFFLINE=1`
  setzen. spaCy-Modell und Datenbank brauchen keine Verbindung.

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
| `ENTITYGUARD_API_KEY` | API-Schlüssel für Headless-Betrieb, zusätzlich zu den Schlüsseln aus dem Admin-UI; mehrere komma-getrennt, mind. 16 Zeichen (kürzere werden ignoriert). Wird nicht gespeichert, Änderung erst nach Neustart. Erzeugen z. B. mit `openssl rand -hex 32` | – |
| `ENTITYGUARD_API_KEY_FILE` | Pfad zu einer Datei mit Schlüssel(n), je Zeile oder komma-getrennt (Docker Secrets, z. B. `/run/secrets/entityguard_api_key`) | – |
| `ENTITYGUARD_ADMIN_PASSWORD` | Passwort des Admin-Kontos; beim Start wird das Konto angelegt bzw. Passwort, Rolle `admin` und Aktiv-Status gesetzt (mind. 8 Zeichen). Überschreibt UI-Änderungen bei jedem Neustart | – |
| `ENTITYGUARD_ADMIN_PASSWORD_FILE` | Wie oben, aus Datei (Docker Secret) | – |
| `ENTITYGUARD_ADMIN_USERNAME` | Benutzername für `ENTITYGUARD_ADMIN_PASSWORD` | `admin` |
| `ENTITYGUARD_MODELS` | Transformer-Modelle, die beim Start aktiv sind (alle anderen werden ausgeschaltet): `fhswf`, `openmed_small`, `openmed_base`, `openmed_large` bzw. voller Registry-Name, komma-getrennt; `none` = alle aus. Nicht gesetzt = Schalter aus `/admin/modelle` bleiben unverändert | – |
| `ENTITYGUARD_OCR_ENABLED` | Bildverarbeitung an/aus; überschreibt `/admin/ocr` | `true` |
| `ENTITYGUARD_OCR_ENGINE` | `auto`, `tesseract` oder `rapidocr`; `auto` nutzt RapidOCR nur bei CUDA, sonst Tesseract | `auto` |
| `ENTITYGUARD_OCR_DEVICE` | RapidOCR-Gerät: `auto`, `cpu`, `cuda`. Ohne CUDA fällt `cuda` auf Tesseract zurück | `auto` |
| `ENTITYGUARD_OCR_LANG` | Tesseract-Sprachen (z. B. `deu+eng`) | `deu+eng` |
| `ENTITYGUARD_OCR_REDACTION` | `entity`, `line` oder `all_text` | `line` |
| `ENTITYGUARD_OCR_MIN_CONFIDENCE` | Mindest-Konfidenz (0–1) | `0.5` |
| `ENTITYGUARD_OCR_VERIFY` | Redigiertes Bild erneut per OCR prüfen; Rest-Treffer = Fail-Closed | `false` |
| `ENTITYGUARD_IMAGE_MAX_BYTES` | Maximale Bildgröße in Bytes | `10485760` |
| `ENTITYGUARD_IMAGE_MAX_PIXELS` | Maximale Pixelzahl | `40000000` |
| `ENTITYGUARD_OCR_TIMEOUT_SECONDS` | OCR-Zeitlimit in Sekunden | `30` |
| `ENTITYGUARD_TESSERACT_CMD` | Optionaler Pfad zum Tesseract-Binary | `tesseract` |
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
│   ├── cstm_analyzer.py         CustomAnalyzer (Presidio + spaCy)
│   │                            DatabasePatternProvider (DB → PatternRecognizer)
│   ├── ocr.py                   Tesseract/RapidOCR-Abstraktion
│   └── image_sanitizer.py       OCR-Text, Span→Box-Mapping, Schwärzung, PNG
│
├── backend/database/
│   ├── models.py                EntityModel, PatternModel, ContextWordModel, DetectorModel, AdminUser, AppSettingModel
│   ├── crud.py                  CRUD-Operationen
│
├── backend/admin/               Admin-UI-Routen (Jinja2, Session-Auth)
│
├── frontend/                    Statische Assets & Templates
│   ├── static/                  CSS, JS
│   └── templates/               Jinja2-Templates (Admin-UI, Sanitize-Seite)
│
├── integrations/openwebui/      Fertiger OpenWebUI-Filter (Text + Bilder)
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

Bilder durchlaufen denselben Analyzer, nur mit OCR davor:

```
Bild (Base64) → OCR (Tesseract/RapidOCR) → OCR-Text + Boxen
      │
      ▼
CustomAnalyzer.analyze_text() → Entitäten + Spans
      │
      ▼
Spans → Boxen (Zeile oder Wort) → schwarze Overlays → PNG (Base64)
```

**Fail-Closed:** Jeder Fehler in der Pipeline gibt HTTP 500 zurück. Der
unbereinigte Text bzw. das Originalbild erreicht das LLM nie.

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
