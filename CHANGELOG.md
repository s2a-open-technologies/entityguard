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

[Unreleased]: https://github.com/daemolition/guardrails/compare/HEAD