# Audit-Checkliste: EntityGuard (Selbstauskunft)

> Simuliert, wie ein Auditor EntityGuard abklopfen würde. Jede Zeile ist mit
> einer konkreten Fundstelle belegt — keine Vermutungen.
> Status: ✅ implementiert/vorhanden · ⚠️ teilweise/mit Einschränkung ·
> ❌ nicht implementiert/nicht vorhanden. **Stand: siehe Git-Historie; vor
> Wiederverwendung gegen den dann aktuellen Code gegenprüfen — Status kann
> sich ändern.**

## Security

| Prüfpunkt | Status | Fundstelle/Beleg | Kommentar |
|---|---|---|---|
| Passwort-Hashing (Admin/Viewer) | ✅ | `admin_users.password_hash`, bcrypt (`backend/database/crud.py`) | Salt automatisch pro Passwort |
| API-Keys nie im Klartext gespeichert | ✅ | `api_keys.key_hash`, bcrypt (`backend/security.py::generate_api_key`) | Klartext wird nur einmalig beim Erzeugen angezeigt |
| API fail-closed ohne Key | ✅ | `backend/security.py::require_api_key` — keine aktiven Keys ⇒ HTTP 401 | Kein Env-Fallback |
| RBAC mit Rollen | ✅ | `admin_users.role` (`admin`/`viewer`), `require_admin` (`backend/admin/auth.py`) | Viewer erhalten 403 auf mutierenden Routen; UI blendet Buttons aus |
| Mutierende Routen admin-only | ✅ | alle `POST`-Routen in `backend/admin/routes.py` hängen an `require_admin` | Lesen + Sanitize-Seite: `require_auth` |
| Admin-Sanitize-Seite hinter Login | ✅ | `GET /admin/sanitize`, `Depends(require_auth)`; Redirect auf Login | Öffentliche Variante entfernt |
| Selbst-/Letzter-Admin-Schutz | ✅ | `backend/admin/routes.py` (users toggle/role/delete) | Eigenen Zugang und letzten aktiven Admin nicht entfernbar/herabstufbar |
| Audit-Log vorhanden & append-only | ✅ | `audit_log` (Migration `018`), `log_audit(...)` | Speichert **keine** geänderten Werte |
| Fehlgeschlagene Logins protokolliert | ✅ | `login_submit` schreibt `login_failed` | Inkl. Client-IP |
| Audit-Export (CSV/JSON) | ✅ | `GET /admin/audit/export?format=csv|json` | Admin-only |
| Request-Tracing ohne Inhalte | ✅ | `request_trace` (Migration `019`), `backend/tracing.py` | Kein Rohtext, kein Mapping; Retention `TRACE_RETENTION_DAYS` |
| Tracing per Konfiguration abschaltbar | ✅ | `TRACE_ENABLED` (`backend/config.py`) | Default an |
| Automatische Trace-Löschung | ✅ | `main.py::_cleanup_request_traces` beim Start | Default 7 Tage |
| Secrets nie im Repo | ✅ | `.gitignore` (`.env`, `data/`); keine hartkodierten Keys | API-Keys/Passwörter nur gehasht in DB |
| Security-Header (HSTS etc.) | ❌ | nicht in `main.py` gesetzt | Betreiber muss sie am Reverse Proxy setzen (siehe `SECURITY.md`) |
| TLS in der Anwendung | ❌ (Betreiber) | `main.py` hört auf Port 9500 ohne TLS | Reverse Proxy erforderlich, sonst Klarnamen im Transit |
| Rate-Limiting / Brute-Force-Schutz | ❌ | kein Limiter vorhanden | Login-Route und `/api/v1/*` über Reverse Proxy/Gateway schützen |
| Multi-Faktor-Authentifizierung | ❌ | nicht implementiert | — |
| Container läuft als Root | ⚠️ | `Dockerfile` setzt keinen `USER` | Basis `python:3.13-slim`, Standard root — Härtung empfohlen |
| Datenbank unverschlüsselt | ⚠️ | SQLite `data/entityguard.db` ohne Feldverschlüsselung | Enthält keine Patientendaten, aber Konfig/Metadaten — Dateisystem schützen |
| Sessions serverseitig persistent | ❌ | in-memory `_sessions` (`backend/admin/auth.py`) | Neustart meldet alle ab; Multi-Instance ungeeignet |
| SQL-Injection-Schutz | ✅ | SQLAlchemy ORM durchgängig | Keine rohen SQL-String-Konkatenationen |
| Abhängigkeiten-Vulnerability-Scan | ⚠️ | keine CI/Scan konfiguriert | Betreiber sollte `uv`-Audit/Dependabot ergänzen |

## Datenschutz / DSGVO

| Prüfpunkt | Status | Fundstelle/Beleg | Kommentar |
|---|---|---|---|
| Datenflussdiagramm / ROPA-Ausgangspunkt | ✅ | [`docs/data-mapping.md`](data-mapping.md) inkl. Mermaid-Flowchart | Explizit als Startpunkt für Art. 30 DSGVO deklariert |
| Art.-32-Maßnahmentabelle | ✅ | `SECURITY.md` „Technical Measures (Article 32)" | Ehrlich mit ⚠️ markiert |
| PII-Maskierung vor LLM | ✅ | Kernzweck; [`docs/pii.md`](pii.md) | Maskierter Text geht ans LLM, `mapping` nur an den Aufrufer |
| Speicherung von Patientendaten | ✅ (minimiert) | Text/Mapping nur flüchtig im Speicher | Durchlauf-Schicht, kein Datenspeicher für Klartext |
| Datenminimierung im Trace | ✅ | nur Metadaten, kein Text/Mapping | `backend/tracing.py` |
| Aufbewahrungsfristen (Trace) | ✅ | `TRACE_RETENTION_DAYS`, Cleanup beim Start | Default 7 Tage |
| Aufbewahrungsfristen (Audit) | ⚠️ | Audit-Log ohne automatisches Ablaufdatum (bewusst) | Enthält keine Patientendaten; manuelle Löschung möglich |
| Eindeutigkeit der PII-Tokens | ✅ | `_index_placeholder` — je Vorkommen indiziert | Verhindert Mapping-Kollisionen |
| „Bekannte Lücken" explizit benannt | ✅ | [`docs/data-mapping.md`](data-mapping.md) Abschnitt „Bekannte Lücken" | Lücken nicht versteckt |
| Recht auf Löschung/Berichtigung/Auskunft | ❌ (entfällt) | EntityGuard speichert keine Betroffenen-Daten | Betroffenenrechte sind beim speichernden System (Aufrufer/openDox) umzusetzen |

## Lizenz / Compliance

| Prüfpunkt | Status | Fundstelle/Beleg | Kommentar |
|---|---|---|---|
| Open-Source-Lizenz | ✅ | `LICENSE` (AGPL-3.0-or-later) | Copyleft — bei SaaS-Betrieb Quelloffenlegungspflicht beachten |
| Disclaimer / Haftung | ✅ | [`DISCLAIMER.md`](../DISCLAIMER.md) | Kein Medizinprodukt; Betreiber verantwortlich |
| Contributing-Leitfaden | ✅ | [`CONTRIBUTING.md`](../CONTRIBUTING.md) | — |
| Verhaltenskodex | ✅ | [`CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md) | Contributor Covenant 2.1 |
| Changelog gepflegt | ✅ | `CHANGELOG.md` (Keep a Changelog) | Release-Workflow in `AGENTS.md` |
