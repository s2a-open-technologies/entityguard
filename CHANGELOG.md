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

### Added

- **Docker-Images auf GHCR** (`ghcr.io/daemolition/entityguard`) für
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

[Unreleased]: https://github.com/daemolition/guardrails/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/daemolition/guardrails/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/daemolition/guardrails/compare/v0.6.0...v1.0.0