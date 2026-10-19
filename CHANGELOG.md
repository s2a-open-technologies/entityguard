# Changelog

All notable changes to EntityGuard are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Versions are bumped via `uv run python scripts/bump_version.py` (patch/minor/major)
and tagged in git (`--commit` flag), which also moves this file's
`[Unreleased]` section under the new version heading. Pushing the resulting
`vX.Y.Z` tag triggers `.github/workflows/release.yml`, which attaches that
section as the GitHub Release notes.

## [Unreleased]

## [1.2.0] — 2026-10-19

### Added

- Bild-Redaktion: `POST /api/v1/sanitize/image` liest Text per OCR (Tesseract oder RapidOCR),
  nutzt dieselbe Entitätserkennung wie Text und liefert ein redigiertes PNG (Base64) plus
  OCR-Text, `mapping` und Boxen. Standard ist zeilenweises Schwärzen; `entity` und `all_text`
  sind wählbar. Bilder werden nur im Speicher verarbeitet, nie gespeichert; bei Fehlern wird
  kein Originalbild zurückgegeben (fail-closed).
- Admin-Seite **Bild-OCR** (`/admin/ocr`) und `app_settings` (Migration `020`): Engine
  (`auto`/`tesseract`/`rapidocr`), Gerät (`auto`/`cpu`/`cuda`), Sprache, Schwärzungsmodus,
  Konfidenz, Verifikation, Größen-/Pixel-Limits und Timeout. `ENTITYGUARD_OCR_*`- und
  `ENTITYGUARD_IMAGE_*`-Umgebungsvariablen überschreiben die Admin-Werte für Headless-Container.
- Admin-Testseite `/admin/sanitize` mit Text-/Bild-Modus: links Original mit roten Markierungen,
  rechts das redigierte PNG, darunter maskierter OCR-Text, Engine/Gerät/Konfidenz und Maskenzahl.
- OpenWebUI-Filter behandelt Bildteile (`image_url`/`input_image`): `image_mode=block`
  (Default, fail-closed) oder `image_mode=redact` (OCR + Schwärzung). Externe Bild-URLs werden
  nicht abgerufen. Fertiger Filter inkl. Kurzanleitung unter
  `integrations/openwebui/entityguard_filter.py` und `integrations/openwebui/README.md`.
- `backend/components/ocr.py` und `backend/components/image_sanitizer.py` mit Tests für
  Engine-Fallback, OCR-Normalisierung, Span→Box-Mapping, Limits und Fail-Closed.
- `reuse_placeholders` (Request-Feld von `POST /api/v1/sanitize`, Standard `false`): Identische
  Werte bekommen im ganzen Text denselben Platzhalter (`[NAME_1]` für jedes „Max Mustermann“),
  das `mapping` hat einen Eintrag je Wert. Gedacht für Aufrufer, die ein ganzes Gespräch in einem
  Aufruf schicken. Ohne das Feld bleibt alles wie bisher.
- OpenWebUI-Filter „Ganzer Kontext in einem Aufruf“ (`docs/OpenWebUI.md`): maskiert System-Prompt,
  Verlauf und neue Frage gemeinsam und übersetzt die Antwort zurück; ersetzt die Einschränkung
  „nur die aktuelle Anfrage“ der einfachen Filter.
- Erste Tests (`tests/`): Platzhalter-Logik ohne spaCy, API mit Fake-Analyzer.
- API-Schlüssel per Umgebungsvariable `ENTITYGUARD_API_KEY` (mehrere komma-getrennt) oder
  `ENTITYGUARD_API_KEY_FILE` (Docker Secret) für den Headless-Betrieb ohne Admin-UI. Gilt
  zusätzlich zu den DB-Schlüsseln, wird nicht gespeichert, in konstanter Zeit verglichen und im
  Trace nur als Präfix `env` geführt; Schlüssel unter 16 Zeichen werden ignoriert. Die Seite
  **API-Schlüssel** zeigt, wie viele Env-Schlüssel aktiv sind. Ohne DB- und Env-Schlüssel bleibt
  die API geschlossen (HTTP 401).
- Admin-Passwort per `ENTITYGUARD_ADMIN_PASSWORD` (oder `_FILE`, optional
  `ENTITYGUARD_ADMIN_USERNAME`, Standard `admin`): Beim Start wird das Konto angelegt bzw. als
  aktiver Admin mit diesem Passwort gesetzt, sodass headless kein `admin`/`admin` übrig bleibt.
  Die Umgebung ist maßgeblich (UI-Änderungen werden beim Neustart überschrieben); Änderungen
  landen im Audit-Log mit Akteur `ENV`.
- Transformer-Modelle per `ENTITYGUARD_MODELS` beim Start aktivieren (`fhswf`, `openmed_small`,
  `openmed_base`, `openmed_large` oder voller Registry-Name, komma-getrennt; `none` = alle aus).
  Genau die genannten Modelle werden eingeschaltet, alle anderen aus; unbekannte Namen werden
  geloggt und ignoriert. Die Seite **Modelle** weist darauf hin.
- `.github/workflows/ghcr-cleanup.yml`: wöchentliches Aufräumen verwaister
  `sha256:…`-Versionen im GHCR-Paket (Multi-Arch-fähig, getaggte Images samt
  Plattform-Images und Attestations bleiben erhalten). Manuell mit Dry-Run
  startbar.

### Fixed

- **Mapping-Kollision bei gemeinsamem Platzhalter**: Teilen sich zwei Entitätstypen einen Platzhalter
  (z. B. IBAN und der Fallback `[SENSITIV]`), wurde je Typ gezählt und es entstand zweimal
  `[SENSITIV_1]`; der zweite Eintrag überschrieb den ersten im `mapping`, die De-Anonymisierung setzte
  den falschen Wert ein. Es wird jetzt je Platzhalter gezählt.
- **`/api/v1/sanitize`, `/api/v1/reload` und `/admin/sanitize/api` blockierten den Server**: Die
  CPU-gebundene Analyse lief als `async def` im Event-Loop und hielt währenddessen alle anderen
  Anfragen an, auch `/health` (Docker-Healthcheck). Die Endpunkte laufen jetzt im Threadpool; die
  Erzeugung des Analyzers ist per Lock gegen doppelte Modellladung bei gleichzeitigen ersten
  Anfragen geschützt.

### Changed

- Neue Laufzeit-Abhängigkeiten `Pillow`, `pytesseract`, `rapidocr` und `onnxruntime`; das
  Dockerfile installiert `tesseract-ocr` samt `deu`/`eng`. Build-Arg `OCR_VARIANT=gpu` tauscht
  `onnxruntime` gegen `onnxruntime-gpu` für RapidOCR auf CUDA.
- Dokumentiert, dass Trennmarken zwischen mehreren Texten **keine Buchstaben** enthalten sollten:
  Die deutsche spaCy-NER hat `=====MSG-1=====` teilweise als Entität erkannt (`MSG-1=====`) und die
  Marke zerstört, `=====#1=====` übersteht die Erkennung (gemessen mit `de_core_news_lg`).

## [1.1.1] — 2026-10-06

### Added

- **Docker-Images auf GHCR** (`ghcr.io/s2a-open-technologies/entityguard`) für
  `linux/amd64` und `linux/arm64`, gebaut durch `.github/workflows/docker.yml`
  (Tag `vX.Y.Z` → `X.Y.Z`, `X.Y`, `X`, `latest`; `master` → `edge`). Zweite
  Variante mit CPU-only torch unter Suffix `-cpu` (`TORCH_VARIANT=cpu`).
  Smoke-Test (`/health`) vor dem Push.
- `.dockerignore`, `.env.example` und Dependabot-Konfiguration für GitHub
  Actions (SHA-gepinnt) und Docker-Basisimage.

### Changed

- **Container**: läuft als Nicht-root-Benutzer, uv-Version gepinnt,
  `alembic upgrade head` beim Containerstart statt beim Build (bestehende
  Volumes werden bei Image-Updates migriert), `HF_HOME` im Datenvolume.
  `docker-compose.yml` nutzt das GHCR-Image und deklariert das Volume.

- **Compliance- und Policy-Dokumentation**: `SECURITY.md` (Sicherheits-
  architektur, Art.-32-Maßnahmen, Deployment-Hinweise), `DISCLAIMER.md`
  (kein Medizinprodukt, Erkennung nicht fehlerfrei), `CONTRIBUTING.md` und
  `CODE_OF_CONDUCT.md`; `docs/data-mapping.md` (Datenfluss/ROPA-Ausgangspunkt),
  `docs/pii.md` (Maskierungs-Pipeline) und
  `docs/audit-checklist-entityguard.md` (Audit-Selbstauskunft). README um
  Abschnitt „Rechtliches & Compliance" ergänzt.
- **Audit-Log-Ausbau**: Filter nach Zeitraum (`date_from`/`date_to`) und
  **CSV-/JSON-Export** (`GET /admin/audit/export`), admin-only.
- **Reload im Admin-UI**: `POST /admin/reload` (session-authentifiziert,
  `require_admin`) lädt den Analyzer neu, ohne einen API-Key zu benötigen;
  Button auf dem Dashboard. Ergänzt den API-Key-geschützten
  `POST /api/v1/reload`.

### Fixed

- **Container: `attempt to write a readonly database` bei bestehenden
  Volumes**: Volumes aus Images vor dem Nicht-root-Wechsel enthalten
  root-eigene Dateien, die uid 10001 nicht schreiben kann (Migration scheiterte
  z. B. an `UPDATE recognizers …`). Der Entrypoint startet jetzt als root,
  korrigiert den Besitzer von `/app/data` und wechselt per `setpriv` auf den
  unprivilegierten Benutzer (kein `USER` mehr im Dockerfile).
- **README**: Datenbank-Volume war als Bind-Mount beschrieben, ist aber ein
  benanntes Volume.
- **README-Fehlerbehebung**: Der `reload`-Beispielbefehl enthielt den jetzt
  erforderlichen API-Key nicht.

## [1.1.0] — 2026-10-03

### Fixed

- **Medizinische Feldbezeichnungen fälschlich als Name/Ort maskiert**
  (Migration `016`): Die deutsche spaCy-NER tagt isolierte Feldwörter wie
  `Fallnr` (PER), `Fallnummer`/`Fallid`/`Az` (LOC) oder `Patientennummer`
  (PER). Sie erschienen dadurch als `[NAME]`/`[ADRESSE/ORT]` und konnten im
  Fließtext sogar einen folgenden Namen verschlucken. Die Wörter sind jetzt
  vorbelegt in der **Ausnahmeliste**; die eigentliche Nummer wird weiterhin
  von `MEDICAL_CONTEXT` (`fallnummer_generic`) maskiert.
- **Doku an die tatsächliche API-Ausgabe angepasst**: Die Kurzbeispiele in
  `README.md` zeigten eine veraltete, nicht indexierte Maskierung
  (`Patient [NAME]`, `der Charité` als Ort). Sie zeigen jetzt die echte
  Ausgabe inkl. `anrede_name`-Zusammenfassung und `[ORGANISATION_1]`.
  `docs/OpenWebUI.md` nannte den Filter fälschlich `Health Guardrail Filter`
  (korrekt: `EntityGuard Filter`) und erwähnt jetzt, dass das Antwort-`mapping`
  bewusst nicht an das LLM weitergegeben wird.

### Added

- **Benutzerverwaltung mit Rollen** (Migration `018`): `admin_users.role`
  (`admin` | `viewer`). Neue Seite **Benutzer** (`/admin/users`) zum Anlegen,
  Aktivieren/Deaktivieren, Rollenwechsel, Passwort-Reset und Löschen
  (nur Admins). `require_admin` (`backend/admin/auth.py`) schützt alle
  mutierenden Routen; Viewer erhalten 403. Selbst-Deaktivierung/-Löschung/
  Rollenentzug und das Entfernen des letzten aktiven Admins sind gesperrt.
- **Audit-Log** (`audit_log`, Migration `018`): append-only Protokoll *wer/wann/
  was* für alle Konfigurationsänderungen (Entitäten, Muster, Kontextwörter,
  Ausnahmeliste, API-Schlüssel, Modelle, Benutzer) sowie Logins **und
  fehlgeschlagene Logins**. Es speichert **keine** geänderten Werte. Seite
  `/admin/audit` (nur Admins, Filter + Pagination).
- **Anfragen-Tracing (inhaltsfrei)** (`request_trace`, Migration `019`,
  `backend/tracing.py`): pro Anonymisierungs-Anfrage nur Metadaten – Quelle,
  App/Key-Präfix, Eingabelänge, Anzahl und Typ der Maskierungen, Latenz,
  Status und optional ein keyed Input-Hash (HMAC). **Kein** Text, **kein**
  Mapping. Nur `/api/v1/sanitize` wird protokolliert — die Admin-Testseite
  (`/admin/sanitize/api`) bewusst **nicht**, da sie bei jedem Tippen auslöst.
  Steuerung über `backend/config.py` / Env: `TRACE_ENABLED` (Default `true`),
  `TRACE_RETENTION_DAYS` (Default `7`, Löschung beim Start), `TRACE_HMAC_SECRET`
  (Hash nur bei gesetztem Secret). Seite `/admin/traces` (nur Admins).
- **API-Schlüssel für die JSON-API** (Migration `017`): `/api/v1/sanitize` und
  `/api/v1/reload` verlangen jetzt einen Schlüssel
  (`Authorization: Bearer <key>` oder `X-API-Key`). Schlüssel werden im
  Admin-UI unter **API-Schlüssel** erzeugt (`backend/security.py`,
  `backend/admin/routes.py`) – Bezeichnung pro App, mehrere Schlüssel möglich,
  an-/ausschaltbar und löschbar. Gespeichert wird nur der bcrypt-Hash; der
  Klartext wird **einmalig** beim Erzeugen angezeigt. Solange kein aktiver
  Schlüssel existiert, antwortet die API mit **401** (fail-closed).
- **Sanitize-Seite hinter dem Login**: Die bisher öffentliche `/sanitize`-Seite
  ist jetzt `GET /admin/sanitize` und nur für eingeloggte Admins erreichbar.
  Sie spricht den neuen same-origin Proxy `POST /admin/sanitize/api` an
  (Session-Auth), sodass im Browser kein Schlüssel liegt. Der öffentliche
  `public_router` / `backend/views/public.py` entfällt; Sidebar- und
  Dashboard-Links zeigen auf `/admin/sanitize`.
- **README**: Ausnahmeliste, API-Schlüssel-Verwaltung und die
  login-geschützte Testseite dokumentiert; Hinweis ergänzt, dass
  `recognizers_count` ein grober Indikator und kein exakter Entitätszähler ist.
- **OpenWebUI-Doku: Antwort-De-Anonymisierung** — neuer Abschnitt
  „Antwort-De-Anonymisierung mit dem `mapping`" in `docs/OpenWebUI.md`:
  erweiterter Filter-Code, der das `mapping` in `inlet()` im
  `__metadata__`-Dict ablegt und in `outlet()` die Platzhalter der LLM-Antwort
  clientseitig durch die Originalwerte ersetzt (inkl. Einschränkungen: kein
  `/api/chat/completed`, nur aktuelle Anfrage). Beide Filter-Varianten senden
  jetzt den API-Schlüssel via `api_key`-Valve mit.
- **Ausnahmeliste mit sinnvollen Vorbelegungen**: Migration `016` seedet die
  bekannten, von spaCy fehlklassifizierten Feldbezeichnungen (siehe oben),
  sodass der Dienst ab Werk keine Label-Wörter mehr maskiert. Die Einträge
  sind im Admin-UI unter **Ausnahmeliste** sichtbar und editierbar.

### Security

- **`/api/v1/sanitize` und `/api/v1/reload` sind ab Werk gesperrt**: Ohne
  aktiven API-Schlüssel liefern sie 401. Die zuvor öffentliche, login-freie
  `/sanitize`-Seite ist entfernt bzw. hinter den Admin-Login verschoben.
- **Sichtbarkeit nach Rolle**: Viewer sehen in der UI keine mutierenden
  Schaltflächen, und Benutzer-, Audit- und Trace-Seiten sind ausschließlich für
  Admins erreichbar. Der Server erzwingt dies unabhängig von der UI (403).
- **Tracing speichert bewusst keine Inhalte** (kein Rohtext, kein `mapping`) und
  unterliegt einer automatischen Aufbewahrungsfrist – Rohtext-/Mapping-Logging
  wäre mit Blick auf Art. 5/9 DSGVO nicht vertretbar.

## [1.0.0] — 2026-10-02

### Changed

- **Datenmodell vereinfacht: Entitäten sind jetzt die zentrale Einheit**
  (Migration `013`). Die Zwischenebene „Erkennungsregel/Recognizer" ist
  entfernt; Muster und Kontextwörter hängen über `entity_id` direkt an der
  Entität. Damit entfallen die 9 wirkungslosen `spacy_*`/`builtin_*`-
  Platzhalterzeilen, und die Erkennung ist ein Konzept statt vier. Die
  Transformer-Schalter liegen in der neuen Tabelle `detector_models`.
  Admin-UI: Entitäten-Liste → Detailseite je Entität mit Mustern,
  Kontextwörtern und Muster-Tester; „Erkennungsregeln" ist aus der Sidebar
  entfernt.
- **Tote Entitäten mit Default-Mustern versorgt** (Migration `014`):
  `IBAN_CODE` bekommt eine IBAN-Regex (`DE…` → `[SENSITIV]`), das
  Datumsmuster zieht von `MEDICAL_CONTEXT` auf `DATE_TIME` um (Datum wird nun
  `[DATUM/ZEIT]` statt `[MED_IDENTIFIKATOR]`), und die nie erkannte Entität
  `FALLNUMMER` wird entfernt (Fallnummern fängt weiterhin `MEDICAL_CONTEXT`).
  Damit hat nach der Migration jede Entität eine reale Erkennungsquelle.
- **API-Pfade in der Doku korrigiert**: Der Sanitize/Reload-Endpunkt heißt
  `/api/v1/sanitize` bzw. `/api/v1/reload` (nicht `/api/v1/entityguard/*`);
  README, AGENTS und `docs/OpenWebUI.md` waren hier falsch und hätten die
  OpenWebUI-Einbindung brechen lassen.

### Added

- **Anrede-basiertes Personennamen-Muster** (Migration `015`): Die deutsche
  spaCy-NER erkennt Namen wie „Stolz" oft nur isoliert, nicht im Satz
  („Frau Stolz aus …"). Ein Default-Muster `anrede_name` fängt
  Anrede/Titel + großgeschriebenen Namen (`Herr`, `Frau`, `Patient`,
  `Dr.`, `Prof.`, …) deterministisch — auch ohne KI-Modell. Der Name-Teil
  nutzt `(?-i:…)`, damit Presidios globales IGNORECASE keine Kleinschreibung
  („aus", „ist") verschluckt.
- **Cache-Busting für statische Assets** — `admin.css`/`admin.js` werden mit
  ihrer mtime als Query (`?v=…`) ausgeliefert (`backend/assets.py`,
  Jinja-Global `asset_url`). Vorher blieb nach einem Update die alte
  `admin.js` im Browser-Cache hängen, wodurch z. B. der Regex-Umschalter auf
  der Entitätsseite „ohne Funktion" erschien.
- **Erkennungsquellen-Anzeige** — Entitäten-Liste und -Detailseite zeigen,
  wodurch eine Entität tatsächlich erkannt wird: `Muster`, `spaCy`/`Presidio`
  (Standard-Engines) und `Modell: …` (nur **aktive** Transformer). Entitäten
  ohne jede Quelle werden als **„⚠ nicht erkannt"** hervorgehoben, mit
  Warnhinweis auf der Detailseite.
- **Regex-Vereinfachung**: Muster lassen sich auf der Entitäts-Detailseite
  als **Stichwortliste** eingeben (komma-/zeilengetrennt → automatischer
  Wortgrenzen-Regex, in `patterns.keywords` gespeichert) oder weiterhin als
  Rohregex. Ein-Klick-**Vorlagen** (Telefon DE, IBAN, Datum, PLZ, E-Mail,
  Straße+PLZ Ort) füllen den Regex-Modus; der **Muster-Tester** zeigt Treffer
  mit Position und erlaubt das direkte Übernehmen eines Musters per Klick.
- **Split-View-Sanitize-Seite** (`/sanitize`) — zweispaltige Ansicht: links
  Text schreiben oder `.txt`/`.md` per Button bzw. Drag & Drop laden, rechts
  erscheint die anonymisierte Version live beim Tippen (600 ms Debounce).
  Erkannte Platzhalter sind hervorgehoben, Hover zeigt den Originalwert;
  Entitäts-Chips und Kopieren-Button inklusive. Die Seite füllt die volle
  Fensterhöhe (Eingabe/Ausgabe wachsen mit dem Fenster). Per Sidebar und
  Dashboard-Schnellzugriff erreichbar; die Seite bleibt öffentlich (kein
  Login), eingeloggte Admins sehen die Sidebar.
- **Auswahlbarer Transformer-Modelle** — vier Modelle, verwaltet über eine
  eigene Admin-Seite **Modelle** (`/admin/modelle`) mit einfachen An/Aus-
  Schaltern (Migrations `011`/`012`, Schalter seit `013` in `detector_models`);
  Umschalten baut den Analyzer sofort neu (kein Neustart, kein separater
  Reload):
  - `transformer_ner_fhswf` (fhswf/bert_de_ner, 110M): freie Namen, Orte,
    Organisationen in Fließtext — 65 % → 87 % Recall vs. spaCy allein,
    ~77 ms/CPU-Call, ~14 ms GPU
  - `transformer_pii_openmed_small` (OpenMed PII German 44M): strukturiertes
    PII als Sicherheitsnetz über den Regex-Patterns (Adressen, Geburtsdatum,
    IBAN, E-Mail, Telefon), ~111 ms/CPU-Call, ~18 ms GPU
  - `transformer_pii_openmed_base` (184M, F1 0.963) und
    `transformer_pii_openmed_large` (434M, F1 0.976): genauere Varianten mit
    **„GPU empfohlen"**-Kennzeichnung; ohne CUDA ~167 ms bzw. ~680 ms/CPU-Call
    (Large ~11× langsamer als auf GPU)
  - Alle laufen parallel zu spaCy + Mustern; mehrere Modelle gleichzeitig
    aktiv sind erlaubt. Alle standardmäßig inaktiv (spaCy + Muster: ~6 ms).
    Modell und Entitäts-Zuordnung sind im Code definiert (`BERT_MODEL_REGISTRY`),
    die Admin-Seite schaltet sie nur an/aus.
  - Die Admin-Seite zeigt einen Live-CUDA-Status und je Modell ein
    „GPU empfohlen"-Badge. `scripts/benchmark_all_models.py` erzeugt die
    CPU/GPU-Latenztabelle für alle Registry-Modelle (Subprozess pro Lauf,
    mit Warmup) und belegt damit die GPU-Empfehlung.
- **ORGANIZATION-Entität** (Platzhalter `[ORGANISATION]`) — vorher wurden
  Organisationen-Treffer der Modelle still verworfen, weil die Entität
  fehlte.
- **Changelog- & Release-System** — `CHANGELOG.md` (Keep a Changelog),
  `scripts/bump_version.py` (Version-Bump + CHANGELOG-Verschiebung +
  Git-Tag via `--commit`) und `.github/workflows/release.yml` (Tag-Push →
  GitHub Release mit den Notes aus der CHANGELOG-Sektion).

### Changed

- **Projektstruktur** — Code aufgeteilt in `backend/` (Admin, Analyzer,
  Datenbank, API-Views) und `frontend/` (statische Assets, Jinja2-Templates);
  `main.py` bleibt im Projekt-Root. Alle Imports von `src.*` auf `backend.*`
  umgezogen, Dockerfile- und Tailwind-Build-Pfade angepasst.

### Fixed

- **Transformer-Device-Auswahl auf CPU-Maschinen** — transformers ≥ 4.5x
  lehnt Integer-Devices ab (`-1` für CPU); die Analyzer-Initialisierung
  schlug ohne GPU still fehl. Jetzt: String-Specs (`cpu`/`cuda`) mit
  Auto-Erkennung, optional `BERT_NER_DEVICE` als Override.
- **Leerzeichen-Verlust beim Transformer-Masking** — Modell-Spans enthielten
  führende Leerzeichen, wodurch Wörter im Ausgabetext verklebten
  („Patient[NAME_1]“). Spans werden jetzt getrimmt („Patient [NAME_1]“).

### Security

- Keine sicherheitsrelevanten Änderungen in diesem Release. (Der Fail-Closed-
  Grundsatz von `/api/v1/entityguard/sanitize` ist unverändert.)

[Unreleased]: https://github.com/s2a-open-technologies/entityguard/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/s2a-open-technologies/entityguard/compare/v1.1.1...v1.2.0
[1.1.1]: https://github.com/s2a-open-technologies/entityguard/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/s2a-open-technologies/entityguard/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/s2a-open-technologies/entityguard/compare/v0.6.0...v1.0.0