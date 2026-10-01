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

- **Split-View-Sanitize-Seite** (`/sanitize`) — zweispaltige Ansicht: links
  Text schreiben oder `.txt`/`.md` per Button bzw. Drag & Drop laden, rechts
  erscheint die anonymisierte Version live beim Tippen (600 ms Debounce).
  Erkannte Platzhalter sind hervorgehoben, Hover zeigt den Originalwert;
  Entitäts-Chips und Kopieren-Button inklusive. Die Seite füllt die volle
  Fensterhöhe (Eingabe/Ausgabe wachsen mit dem Fenster). Per Sidebar und
  Dashboard-Schnellzugriff erreichbar; die Seite bleibt öffentlich (kein
  Login), eingeloggte Admins sehen die Sidebar.
- **Auswahlbarer Transformer-Modelle** — zwei Modelle, verwaltet über eine
  eigene Admin-Seite **Modelle** (`/admin/modelle`) mit einfachen An/Aus-
  Schaltern (Migration `011`); Umschalten baut den Analyzer sofort neu
  (kein Neustart, kein separater Reload):
  - `transformer_ner_fhswf` (fhswf/bert_de_ner, 110M): freie Namen, Orte,
    Organisationen in Fließtext — 65 % → 87 % Recall vs. spaCy allein,
    ~89 ms/CPU-Call, ~14–20 ms GPU
  - `transformer_pii_openmed` (OpenMed PII German Small 44M): strukturiertes
    PII als Sicherheitsnetz über den Regex-Patterns (Adressen, Geburtsdatum,
    IBAN, E-Mail, Telefon), ~99 ms/CPU-Call
  - Beide laufen parallel zu spaCy + Patterns; mehrere Modelle gleichzeitig
    aktiv sind erlaubt. Beide standardmäßig inaktiv (spaCy + Patterns: ~6 ms).
    Die Modell-Zeilen sind absichtlich keine bearbeitbaren Erkennungsregeln:
    Modell und Entitäts-Zuordnung sind im Code definiert; die
    Erkennungsregeln-Liste blendet sie aus, Bearbeiten/Löschen leitet auf
    /admin/modelle weiter.
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