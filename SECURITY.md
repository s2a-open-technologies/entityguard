# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.x     | :white_check_mark: |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, please report them via email to: **christopher.abanilla@gmx.de**
(dedicated `security@` alias TBD — replace once one exists).

We will acknowledge receipt of your vulnerability report within 48 hours and
send you regular updates about our progress.

**What to include:**
- Description of the vulnerability
- Steps to reproduce the issue
- Possible impact
- Suggested fix (if any)

**What to expect:**
1. Initial response within 48 hours
2. Assessment within 5 business days
3. Fix timeline and disclosure coordination
4. Credit in security advisory (if desired)

---

# Security Architecture

> This section describes what the code in this repository actually does,
> verified against the source — not aspirational best practice. Items that
> are recommended but **not yet implemented** are explicitly marked as such
> rather than presented as fact.

EntityGuard is a **stateless anonymization layer** for LLM applications in
healthcare. Its security model differs from a typical data-storing app: the
main asset to protect is the *in-transit content* (which may contain patient
data until it is masked), plus the configuration and the audit trail.

## Authentication & Authorization

### Admin UI (HTML) — session-based

The admin UI under `/admin/*` uses server-side sessions:

- Login with username/password; passwords are **bcrypt** hashes
  (`admin_users.password_hash`).
- Sessions are **in-memory** (`backend/admin/auth.py::_sessions`), keyed by a
  `secrets.token_urlsafe(32)` cookie (`admin_session`, `httponly`, `samesite=lax`,
  8h expiry). A restart or missing shared store logs everyone out; not suitable
  for multi-instance deployments without a shared session store.
- **Roles** (`admin_users.role`):
  - `admin` — full access (configuration, users, audit, traces).
  - `viewer` — read-only.
  `require_admin` (`backend/admin/auth.py`) wraps `require_auth` and returns
  **403** for viewers. All mutating routes use `require_admin`.
- The default account `admin` / `admin` is created by migration `004` and
  **must be changed immediately** in production.

### JSON API — API keys

`/api/v1/sanitize` and `/api/v1/reload` require an API key
(`backend/security.py::require_api_key`):

- Sent as `Authorization: Bearer <key>` **or** `X-API-Key: <key>`.
- Keys are created in the admin UI (`/admin/api-keys`); only a **bcrypt hash**
  and a display `key_prefix` are stored. The plaintext is shown **once** at
  creation and cannot be recovered.
- Only **active** keys count. With **no active key configured, every request
  is rejected with HTTP 401** (fail-closed). There is no environment fallback.
- `/health` stays open (health checks).

### CSRF

State-changing API endpoints require an `Authorization`/`X-API-Key` header.
The admin UI uses cookie-based sessions, so admin forms rely on the
`SameSite=Lax` cookie attribute; there is no separate CSRF token. This is
adequate for same-site navigation but worth revisiting if the admin UI is ever
exposed cross-site.

## Data Handling

### What is stored — and what is not

EntityGuard **does not persist the text it sanitizes** and **does not persist
the `mapping`** (placeholder → original). Both exist only in memory for the
duration of a request. See [`docs/data-mapping.md`](data-mapping.md) for the
full picture.

| Table | Content | Encrypted? |
|---|---|---|
| `entities`, `patterns`, `context_words`, `allowed_values` | Detection configuration | ❌ (no patient data) |
| `admin_users` | Username + bcrypt password hash + role | password hashed |
| `api_keys` | App label + key prefix + bcrypt key hash | key hashed |
| `audit_log` | Who/when/what for config changes and logins — **never the changed values** | ❌ |
| `request_trace` | Content-free request metadata (lengths, counts, latency, optional input HMAC) — **never text or mapping** | ❌ |

**No field-level encryption is implemented** (no `ENCRYPTION_KEY`). The SQLite
file contains only configuration and metadata, not patient data, but should
still be protected at the filesystem level.

### Password / key hashing

- Passwords and API keys use **bcrypt** with a per-value salt
  (`backend/database/crud.py`, `backend/security.py`).

### Transport

The application does **not** terminate TLS (`main.py` listens on `0.0.0.0:9500`).
Because the input contains cleartext patient data until masked, **TLS must be
terminated by a reverse proxy** when the service is reachable beyond a trusted
Docker network.

## Audit & Tracing

- **Audit log** (`audit_log`, migration `018`): append-only record of
  *who/when/what* for every configuration change plus successful and failed
  logins. Logins also store the client IP. It never stores changed values.
  Browsable and exportable (CSV/JSON) at `/admin/audit` (admin-only).
- **Request tracing** (`request_trace`, migration `019`,
  `backend/tracing.py`): content-free per-request metadata for
  `/api/v1/sanitize` only (the admin live-preview is deliberately not traced).
  Controlled via `backend/config.py` / env: `TRACE_ENABLED` (default `true`),
  `TRACE_RETENTION_DAYS` (default `7`, pruned on startup in `main.py`),
  `TRACE_HMAC_SECRET` (input hash written only when set). **Never** stores the
  text or the mapping.

## Deployment Security

### Docker

- The image (`Dockerfile`) is based on `python:3.13-slim` and installs the
  spaCy model at build time. **It does not set a `USER`, so the container runs
  as root** — hardening (non-root user, `read_only`, `cap_drop`) is recommended
  but not currently applied.
- `docker-compose.yml` maps `9500:9500` and uses a **named volume**
  `entityguard-data` for the SQLite database, so data persists across
  `docker-compose down`. No host bind-mount of the local `data/` dir.
- The container health check hits `localhost:9500/health`.

### Reverse proxy

TLS and security headers (HSTS, `X-Frame-Options`, `X-Content-Type-Options`,
`Referrer-Policy`) are **not** set by the app and must come from the reverse
proxy. Recommended baseline:

```apache
<VirtualHost *:443>
    ServerName entityguard.example.com

    SSLEngine on
    SSLCertificateFile /etc/apache2/ssl/entityguard.crt
    SSLCertificateKeyFile /etc/apache2/ssl/entityguard.key

    # Overwrite, don't append — a client-supplied value would otherwise pass through.
    RequestHeader set X-Forwarded-Proto "https"
    RequestHeader set X-Forwarded-For   %{REMOTE_ADDR}s

    ProxyPass        "/" "http://127.0.0.1:9500/"
    ProxyPassReverse "/" "http://127.0.0.1:9500/"

    Header always set Strict-Transport-Security "max-age=31536000; includeSubDomains"
    Header always set X-Frame-Options "SAMEORIGIN"
    Header always set X-Content-Type-Options "nosniff"
    Header always set Referrer-Policy "strict-origin-when-cross-origin"
</VirtualHost>
```

Required Apache modules: `a2enmod proxy proxy_http ssl headers`.

### Not implemented (operator responsibility)

- **Rate limiting / brute-force protection**: none in the app. Put `/admin/login`
  and `/api/v1/*` behind a rate-limiting reverse proxy or gateway.
- **Multi-factor authentication**: not implemented anywhere.
- **Persistent sessions**: in-memory only (see above).
- **Automatic retention for the audit log**: append-only by design.

---

# Security Checklist

## Pre-Deployment

- [ ] Admin password changed from the default `admin`/`admin`
- [ ] At least one **active API key** created under `/admin/api-keys` (otherwise the API is closed)
- [ ] Only necessary accounts exist; roles reviewed (`/admin/users`)
- [ ] HTTPS terminated at the reverse proxy (cleartext patient data is in the request body)
- [ ] `TRACE_HMAC_SECRET` set if input correlation is required; otherwise tracing stays metadata-only
- [ ] `TRACE_RETENTION_DAYS` matches your retention policy
- [ ] Docker container hardened (non-root user, dropped capabilities)
- [ ] Filesystem permissions on `data/entityguard.db` restrict access to the service account

## Post-Deployment

- [ ] `/health` reachable; security headers present in responses
- [ ] Certificate valid and not expiring soon
- [ ] Database backups encrypted (if backups are taken)
- [ ] No secrets in logs
- [ ] Audit log (`/admin/audit`) reachable and populated

## Regular Maintenance

- [ ] Review audit log periodically
- [ ] Rotate API keys (deactivate/delete + recreate) on suspicion
- [ ] Review user permissions and roles
- [ ] Update dependencies (check for CVEs)
- [ ] Prune or export the audit log as needed (no auto-expiry)

---

# GDPR Compliance

> This section describes what is and isn't implemented today — verified
> against the code, not aspirational. For the full data-flow picture see
> [`docs/data-mapping.md`](data-mapping.md). None of this is legal advice.

## Technical Measures (Article 32)

| Measure | Implementation | Status |
|---------|---------------|--------|
| Data minimization | Text and `mapping` are never persisted; traces are metadata-only | ✅ |
| Pseudonymization before the LLM | Masking is the core function; the LLM sees only masked text | ✅ |
| Access control | Session auth + roles; API keys (bcrypt, fail-closed) | ✅ |
| Audit trail | Append-only `audit_log` incl. failed logins | ✅ |
| Retention limitation | Trace auto-pruned (`TRACE_RETENTION_DAYS`) | ✅ (trace only) |
| Encryption in transit | Not enforced by the app — must come from the reverse proxy | ⚠️ |
| Encryption at rest | None (SQLite holds no patient data) | ⚠️ |
| Availability | Backups are the operator's responsibility | ⚠️ |

## Organizational Measures

Outside this repository's scope — operator responsibility:

- [ ] **Privacy Policy** published and accessible
- [ ] **Data Processing Agreement (DPA)** with the hosting provider and any externally-configured LLM endpoint
- [ ] **Records of Processing Activities (ROPA)** documented — use [`docs/data-mapping.md`](data-mapping.md) as a starting point
- [ ] **Data Retention Policy** defined (EntityGuard stores no patient data; traces auto-expire; the audit log does not)
- [ ] **Breach Notification Procedure** (72h to authorities)
- [ ] Betroffenenrechte (Auskunft/Löschung/Berichtigung) are handled by the *storing* system (e.g. openDox), since EntityGuard stores no data-subject data

---

# Security Best Practices

## For Administrators

1. **Change the default admin password** immediately (`admin`/`admin`).
2. Use **strong, unique passwords**; one account per person.
3. Grant `viewer` to people who only need to look, `admin` sparingly.
4. **Create API keys per app** and deactivate/delete them when an app is retired.
5. **Terminate TLS** at the reverse proxy — the request body contains cleartext patient data until masked.
6. **Protect the SQLite file** (`data/entityguard.db`) at the filesystem level.
7. **Monitor the audit log** for unexpected configuration changes or failed logins.

## For Developers

1. **Never commit secrets** — no `.env` with keys in Git; API keys/passwords live hashed in the DB.
2. **Validate inputs** with Pydantic models.
3. **Use the ORM** — SQLAlchemy prevents SQL injection.
4. **Never log request text or the `mapping`** — tracing must stay content-free.
5. **Keep `/api/v1/*` fail-closed** — no silent pass-through on error (HTTP 500) and no unauthenticated access (HTTP 401).
6. **Add tests** under `tests/` for security-relevant changes (currently none exist).

## For End Users

1. Lock your workstation when away.
2. Don't share admin credentials.
3. Log out when finished.
4. Report suspicious activity immediately.

---

# Incident Response

## Severity Levels

| Level | Description | Examples | Response Time |
|-------|-------------|----------|---------------|
| **Critical** | Active exploitation, data breach | Unauthorized admin access, key leak enabling data exfiltration | Immediate |
| **High** | Potential breach, severe vulnerability | Auth bypass, fail-open masking | 24 hours |
| **Medium** | Security weakness, no active exploitation | Information disclosure, verbose errors | 7 days |
| **Low** | Best practice deviation | Missing header, outdated TLS | Next release |

## Response Playbook

### Critical Incident

1. **Contain** (0-1 hour)
   - Deactivate all API keys (`/admin/api-keys`) to cut off the API
   - Deactivate affected accounts (`/admin/users`)
   - Take the service offline if needed (it stores no patient data, so there is no data store to freeze)

2. **Assess** (1-4 hours)
   - Determine scope of exposure (was cleartext in transit intercepted? were keys leaked?)
   - Preserve `audit_log` and `request_trace` as evidence

3. **Notify** (4-72 hours)
   - Internal stakeholders
   - Data protection authority (if required)
   - Affected parties (if required)

4. **Remediate** (ongoing)
   - Rotate all API keys and admin passwords
   - Patch vulnerabilities

5. **Review** (post-incident)
   - Root cause analysis
   - Process improvements

---

# Contact

**Security Contact:**
- Email: christopher.abanilla@gmx.de (dedicated `security@` alias TBD)

**Responsible Disclosure:**
We follow a 90-day disclosure policy. After fix confirmation, we will:
1. Issue security advisory
2. Credit reporter (if desired)
3. Update this document

---

# References

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
- [GDPR Guidelines](https://gdpr.eu/)
- [Docker Security](https://docs.docker.com/engine/security/)
- [`docs/data-mapping.md`](docs/data-mapping.md) — full data-flow mapping
- [`docs/pii.md`](docs/pii.md) — masking pipeline detail
- [`docs/audit-checklist-entityguard.md`](docs/audit-checklist-entityguard.md) — audit self-assessment
- `AGENTS.md` — technical architecture reference

---

*Version: 1.0 — reconciled against the v1.1.0 codebase*
