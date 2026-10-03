"""
.
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

import json
import logging
import re
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from backend.components.bert_recognizer import BERT_MODEL_REGISTRY, gpu_available
from backend.components.cstm_analyzer import CustomAnalyzer
from backend.assets import asset_url
from backend.config import TRACE_ENABLED, TRACE_RETENTION_DAYS
from backend.database import SessionLocal
from backend.database.crud import (
    count_active_admins, count_audit_logs, count_request_traces,
    create_allowed_value, create_admin_user, create_api_key, create_context_word, create_entity,
    create_pattern,
    delete_admin_user, delete_allowed_value, delete_api_key, delete_context_word, delete_entity,
    delete_pattern,
    get_admin_user, get_admin_user_by_username, get_admin_users, get_allowed_values,
    get_allowed_value_by_value, get_api_keys,
    get_api_key, get_audit_logs, get_context_word, get_context_words_by_entity, get_entities,
    get_entity, get_entity_by_name, get_pattern, get_pattern_by_name, get_patterns_by_entity,
    get_detector_models, get_request_traces, log_audit, set_admin_user_active, set_api_key_active,
    set_detector_model_active, update_admin_password, update_admin_role, update_entity,
    update_pattern, verify_password,
)
from backend.security import generate_api_key

from .auth import (
    authenticate_user, create_session, delete_session, require_admin, require_auth,
    SESSION_COOKIE_NAME,
)
from .dependencies import get_template_context

# Router
admin_router = APIRouter(prefix="/admin", tags=["Admin"])

# Logger
logger = logging.getLogger("uvicorn.error")

# Templates
TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "frontend" / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)
templates.env.globals["asset_url"] = asset_url

# Valid user roles.
VALID_ROLES = ("admin", "viewer")


def _client_ip(request: Request) -> str | None:
    """Best-effort client IP for the audit log."""
    if request.client:
        return request.client.host
    return None


class SanitizePageRequest(BaseModel):
    """Request body for the session-authenticated sanitize proxy."""
    text: str


# Entities detected by built-in Presidio engines (independent of DB patterns
# and transformer models). Verified against the German spaCy pipeline - its
# NER only emits PER/LOC/ORG - plus the Presidio recognizers kept by
# CustomAnalyzer._remove_builtin_recognizers (Email/Phone). Deliberately a
# static map, not introspection: SpacyRecognizer advertises DATE_TIME /
# PHONE_NUMBER / EMAIL in supported_entities although the German model never
# produces them, and Date/Iban recognizers are removed on startup.
BASE_ENTITY_SOURCES = {
    "PERSON": "spaCy",
    "LOCATION": "spaCy",
    "ORGANIZATION": "spaCy",
    "EMAIL_ADDRESS": "Presidio E-Mail",
    "PHONE_NUMBER": "Presidio Telefon",
}


def _active_model_entity_sources(db) -> dict[str, list[str]]:
    """Map entity name -> active detector models that can detect it."""
    sources: dict[str, list[str]] = {}
    active = {m.name for m in get_detector_models(db) if m.is_active}
    for key in active:
        entry = BERT_MODEL_REGISTRY.get(key)
        if not entry:
            continue
        for entity_name in set(entry["mapping"].values()):
            sources.setdefault(entity_name, []).append(key)
    return sources


def _entity_sources(entity, active_model_sources: dict[str, list[str]]) -> list[str]:
    """Return the human-readable detection sources for one entity.

    Combines DB patterns, built-in Presidio engines (BASE_ENTITY_SOURCES)
    and currently-active transformer models. An entity with an empty list is
    not detected at all.
    """
    sources: list[str] = []
    if len(entity.patterns) > 0:
        sources.append("Muster")
    base = BASE_ENTITY_SOURCES.get(entity.name)
    if base:
        sources.append(base)
    for model in active_model_sources.get(entity.name, []):
        sources.append(f"Modell: {model}")
    return sources


def build_keyword_regex(raw_keywords: str) -> str:
    """Turn a comma/newline separated keyword list into a word-boundary regex.

    Lets admins add simple term lists (e.g. "AOK, TK, Barmer") without
    writing regex; the result is stored as a normal pattern.

    Args:
        raw_keywords: Comma or newline separated terms.

    Returns:
        A case-insensitive regex matching any whole term.
    """
    terms = [t.strip() for t in re.split(r"[,\n;]+", raw_keywords) if t.strip()]
    escaped = [re.escape(t) for t in terms]
    return r"(?i)\b(" + "|".join(escaped) + r")\b"


def _validate_pattern(db, name: str, regex: str, ignore_id: int | None = None) -> str | None:
    """Validate a pattern's name uniqueness and regex syntax."""
    if not name.strip():
        return "Ein Name ist erforderlich"
    if not regex.strip():
        return "Ein Muster (Regex oder Stichwörter) ist erforderlich"
    try:
        re.compile(regex)
    except re.error as e:
        return f"Ungültiger regulärer Ausdruck: {e}"
    existing = get_pattern_by_name(db, name)
    if existing and existing.id != ignore_id:
        return f"Ein Muster mit dem Namen '{name}' existiert bereits"
    return None


# Regex templates offered as one-click chips on the entity detail page.
PATTERN_TEMPLATES = [
    {"label": "Telefon DE", "name": "telefon", "regex": r"(?:\+49|0)[\s/-]?\d{2,5}[\s/-]?\d{3,9}",
     "description": "Deutsche Telefonnummern"},
    {"label": "IBAN", "name": "iban", "regex": r"\bDE\d{2}(?:\s?\d{4}){4}\s?\d{2}\b",
     "description": "Deutsche IBAN"},
    {"label": "Datum", "name": "datum", "regex": r"\b\d{1,2}\.\d{1,2}\.\d{2,4}\b",
     "description": "Datum im Format TT.MM.JJJJ"},
    {"label": "PLZ", "name": "plz", "regex": r"\b\d{5}\b",
     "description": "Fünfstellige Postleitzahl"},
    {"label": "E-Mail", "name": "email", "regex": r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
     "description": "E-Mail-Adresse"},
    {"label": "Straße + PLZ Ort", "name": "adresse",
     "regex": r"(?:[A-ZÄÖÜ][a-zäöüß]+[- ]?){1,3}(?:straße|str\.?|weg|allee|platz|ring|damm|gasse)\s+\d{1,4}[a-zA-Z]?,?\s*\d{5}\s+[A-ZÄÖÜ][a-zA-ZäöüÄÖÜß\-]+",
     "description": "Straße Hausnummer, PLZ Ort"},
]


@admin_router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Render the login page."""
    return templates.TemplateResponse(
        "login.html",
        get_template_context(request)
    )


@admin_router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()]
):
    """Handle login form submission."""
    user_id = authenticate_user(username, password)
    if not user_id:
        db = SessionLocal()
        try:
            log_audit(
                db,
                action="login_failed",
                summary=f"Fehlgeschlagener Login für '{username}'",
                actor_username=username,
                target_type="admin_user",
                ip_address=_client_ip(request),
            )
        finally:
            db.close()
        context = get_template_context(request, error="Ungültiger Benutzername oder ungültiges Passwort")
        return templates.TemplateResponse("login.html", context, status_code=401)

    db = SessionLocal()
    try:
        log_audit(
            db,
            action="login",
            summary=f"Login von '{username}'",
            actor_id=user_id,
            actor_username=username,
            target_type="admin_user",
            target_id=user_id,
            ip_address=_client_ip(request),
        )
    finally:
        db.close()

    session_id = create_session(user_id)
    response = RedirectResponse(url="/admin/dashboard", status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        max_age=8 * 3600,  # 8 hours
        samesite="lax"
    )
    return response


@admin_router.get("/logout")
async def logout(request: Request):
    """Log out the current user."""
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        delete_session(session_id)

    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME)
    return response


# ============================================================================
# Dashboard
# ============================================================================

@admin_router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, user: dict = Depends(require_auth)):
    """Render the admin dashboard."""
    db = SessionLocal()
    try:
        entities = get_entities(db)
        active_count = sum(1 for e in entities if e.is_active)
        total_patterns = sum(len(e.patterns) for e in entities)
        context = get_template_context(
            request,
            entities=entities,
            active_count=active_count,
            total_patterns=total_patterns
        )
        return templates.TemplateResponse("dashboard.html", context)
    finally:
        db.close()


# ============================================================================
# Anleitung (HowTo)
# ============================================================================

@admin_router.get("/howto", response_class=HTMLResponse)
async def howto_page(request: Request, user: dict = Depends(require_auth)):
    """Render the HowTo / guide page."""
    return templates.TemplateResponse(
        "howto.html",
        get_template_context(request)
    )


# ============================================================================
# Preview (regex tester, shared by entity detail + pattern edit)
# ============================================================================

@admin_router.post("/preview")
async def preview_pattern(
    request: Request,
    text: Annotated[str, Form()],
    pattern: Annotated[str, Form()],
    user: dict = Depends(require_auth)
):
    """Preview how a regex matches text, with a short explanation."""
    try:
        compiled = re.compile(pattern)
        matches = list(compiled.finditer(text))
        return {
            "success": True,
            "matches": [
                {"start": m.start(), "end": m.end(), "match": m.group()}
                for m in matches
            ],
            "count": len(matches),
        }
    except re.error as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Profile (Password Change)
# ============================================================================

@admin_router.get("/profile/password", response_class=HTMLResponse)
async def change_password_page(request: Request, user: dict = Depends(require_auth)):
    """Render the change password form."""
    return templates.TemplateResponse(
        "profile/password.html",
        get_template_context(request)
    )


@admin_router.post("/profile/password")
async def change_password_submit(
    request: Request,
    current_password: Annotated[str, Form()],
    new_password: Annotated[str, Form()],
    confirm_password: Annotated[str, Form()],
    user: dict = Depends(require_auth)
):
    """Change the admin user's password."""
    db = SessionLocal()
    try:
        # Verify current password
        db_user = get_admin_user(db, user["id"])
        if not db_user:
            raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")

        if not verify_password(current_password, db_user.password_hash):
            context = get_template_context(request, error="Das aktuelle Passwort ist falsch")
            return templates.TemplateResponse("profile/password.html", context, status_code=400)

        # Validate new password
        if len(new_password) < 8:
            context = get_template_context(request, error="Das Passwort muss mindestens 8 Zeichen lang sein")
            return templates.TemplateResponse("profile/password.html", context, status_code=400)

        if new_password != confirm_password:
            context = get_template_context(request, error="Die Passwörter stimmen nicht überein")
            return templates.TemplateResponse("profile/password.html", context, status_code=400)

        # Update password
        update_admin_password(db, user["id"], new_password)
        log_audit(
            db, action="password_change", summary="Eigenes Passwort geändert",
            actor_id=user["id"], actor_username=user["username"],
            target_type="admin_user", target_id=user["id"], target_label=user["username"],
            ip_address=_client_ip(request),
        )

        context = get_template_context(request, success="Passwort erfolgreich geändert")
        return templates.TemplateResponse("profile/password.html", context)
    finally:
        db.close()


# ============================================================================
# Allow-List
# ============================================================================

@admin_router.get("/allowlist", response_class=HTMLResponse)
async def list_allowed_values(request: Request, user: dict = Depends(require_auth)):
    """Render the allow-list."""
    db = SessionLocal()
    try:
        allowed_values = get_allowed_values(db)
        context = get_template_context(request, allowed_values=allowed_values)
        return templates.TemplateResponse("allowlist/list.html", context)
    finally:
        db.close()


@admin_router.post("/allowlist/create")
async def create_allowed_value_submit(
    request: Request,
    value: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    user: dict = Depends(require_admin)
):
    """Add a new allow-listed value."""
    db = SessionLocal()
    try:
        existing = get_allowed_value_by_value(db, value)
        if existing:
            allowed_values = get_allowed_values(db)
            context = get_template_context(
                request,
                allowed_values=allowed_values,
                error=f"'{value}' ist bereits in der Ausnahmeliste"
            )
            return templates.TemplateResponse("allowlist/list.html", context, status_code=400)

        create_allowed_value(db, value=value, description=description if description else None)
        log_audit(
            db, action="create", summary=f"Ausnahmeliste: '{value}' hinzugefügt",
            actor_id=user["id"], actor_username=user["username"],
            target_type="allowed_value", target_label=value, ip_address=_client_ip(request),
        )
        return RedirectResponse(url="/admin/allowlist", status_code=303)
    finally:
        db.close()


@admin_router.post("/allowlist/{allowed_value_id}/delete")
async def delete_allowed_value_submit(
    request: Request,
    allowed_value_id: int,
    user: dict = Depends(require_admin)
):
    """Delete an allow-listed value."""
    db = SessionLocal()
    try:
        entry = get_allowed_values(db)
        label = next((a.value for a in entry if a.id == allowed_value_id), str(allowed_value_id))
        delete_allowed_value(db, allowed_value_id)
        log_audit(
            db, action="delete", summary=f"Ausnahmeliste: '{label}' gelöscht",
            actor_id=user["id"], actor_username=user["username"],
            target_type="allowed_value", target_id=allowed_value_id, target_label=label,
            ip_address=_client_ip(request),
        )
        return RedirectResponse(url="/admin/allowlist", status_code=303)
    finally:
        db.close()


# ============================================================================
# API Keys
# ============================================================================

@admin_router.get("/api-keys", response_class=HTMLResponse)
async def list_api_keys(request: Request, user: dict = Depends(require_auth)):
    """Render the API-keys page."""
    db = SessionLocal()
    try:
        api_keys = get_api_keys(db)
        context = get_template_context(
            request,
            api_keys=api_keys,
            new_api_key=request.query_params.get("new_key"),
        )
        return templates.TemplateResponse("apikeys/list.html", context)
    finally:
        db.close()


@admin_router.post("/api-keys/create")
async def create_api_key_submit(
    request: Request,
    name: Annotated[str, Form()],
    user: dict = Depends(require_admin)
):
    """Create a new API key and show its plaintext exactly once."""
    name = name.strip()
    if not name:
        db = SessionLocal()
        try:
            context = get_template_context(
                request,
                api_keys=get_api_keys(db),
                error="Eine Bezeichnung ist erforderlich",
            )
            return templates.TemplateResponse("apikeys/list.html", context, status_code=400)
        finally:
            db.close()

    plaintext, prefix, key_hash = generate_api_key(name)
    db = SessionLocal()
    try:
        create_api_key(db, name=name, key_prefix=prefix, key_hash=key_hash)
        log_audit(
            db, action="create", summary=f"API-Schlüssel für '{name}' erzeugt",
            actor_id=user["id"], actor_username=user["username"],
            target_type="api_key", target_label=prefix, ip_address=_client_ip(request),
        )
        return RedirectResponse(url=f"/admin/api-keys?new_key={plaintext}", status_code=303)
    finally:
        db.close()


@admin_router.post("/api-keys/{api_key_id}/toggle")
async def toggle_api_key_submit(
    request: Request,
    api_key_id: int,
    user: dict = Depends(require_admin)
):
    """Activate or deactivate an API key."""
    db = SessionLocal()
    try:
        api_key = get_api_key(db, api_key_id)
        if api_key:
            new_state = not api_key.is_active
            set_api_key_active(db, api_key_id, new_state)
            log_audit(
                db,
                action="toggle",
                summary=f"API-Schlüssel '{api_key.name}' {'aktiviert' if new_state else 'deaktiviert'}",
                actor_id=user["id"], actor_username=user["username"],
                target_type="api_key", target_id=api_key_id, target_label=api_key.key_prefix,
                ip_address=_client_ip(request),
            )
        return RedirectResponse(url="/admin/api-keys", status_code=303)
    finally:
        db.close()


@admin_router.post("/api-keys/{api_key_id}/delete")
async def delete_api_key_submit(
    request: Request,
    api_key_id: int,
    user: dict = Depends(require_admin)
):
    """Delete an API key."""
    db = SessionLocal()
    try:
        api_key = get_api_key(db, api_key_id)
        label = api_key.key_prefix if api_key else str(api_key_id)
        delete_api_key(db, api_key_id)
        log_audit(
            db, action="delete", summary=f"API-Schlüssel '{label}' gelöscht",
            actor_id=user["id"], actor_username=user["username"],
            target_type="api_key", target_id=api_key_id, target_label=label,
            ip_address=_client_ip(request),
        )
        return RedirectResponse(url="/admin/api-keys", status_code=303)
    finally:
        db.close()


# ============================================================================
# Sanitize (login-protected; server-side proxy to the analyzer)
# ============================================================================

@admin_router.get("/sanitize", response_class=HTMLResponse)
async def sanitize_page(request: Request, user: dict = Depends(require_auth)):
    """Render the text-sanitization page (login required).

    The page talks to /admin/sanitize/api on the same origin, so the admin
    session is used instead of an API key - nothing key-like is exposed to
    the browser.
    """
    return templates.TemplateResponse("sanitize.html", get_template_context(request))


@admin_router.post("/sanitize/api")
async def sanitize_api(
    request: Request,
    payload: SanitizePageRequest,
    user: dict = Depends(require_auth)
):
    """Sanitize text for the admin UI (session-authenticated, same-origin).

    Mirrors the /api/v1/sanitize behaviour but authenticates via the admin
    session rather than an API key, so the web UI keeps working without
    exposing a key to the browser. Deliberately not traced: this page fires
    one request per typing pause (live preview), which would flood the trace
    log - only real API calls are recorded.
    """
    import backend.views.anonymizer as anonymizer_module

    try:
        analyzer = anonymizer_module._get_or_create_analyzer()
        sanitized_text, mapping = analyzer.process_text(payload.text)
        return {"sanitized_text": sanitized_text, "mapping": mapping}
    except Exception as e:
        logger.error(f"Error in admin sanitize proxy: {e}")
        raise HTTPException(
            status_code=500,
            detail="Security abort: Data sanitization failed"
        )


# ============================================================================
# Entities
# ============================================================================

@admin_router.get("/entities", response_class=HTMLResponse)
async def list_entities(request: Request, user: dict = Depends(require_auth)):
    """Render the list of entities."""
    db = SessionLocal()
    try:
        entities = get_entities(db)
        model_sources = _active_model_entity_sources(db)
        pattern_counts = {e.id: len(e.patterns) for e in entities}
        entity_sources = {e.id: _entity_sources(e, model_sources) for e in entities}
        context = get_template_context(
            request,
            entities=entities,
            pattern_counts=pattern_counts,
            entity_sources=entity_sources,
        )
        return templates.TemplateResponse("entities/list.html", context)
    finally:
        db.close()


@admin_router.get("/entities/create", response_class=HTMLResponse)
async def create_entity_page(request: Request, user: dict = Depends(require_auth)):
    """Render the create entity form."""
    return templates.TemplateResponse(
        "entities/create.html",
        get_template_context(request)
    )


@admin_router.post("/entities/create")
async def create_entity_submit(
    request: Request,
    name: Annotated[str, Form()],
    placeholder: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    is_active: Annotated[bool, Form()] = True,
    user: dict = Depends(require_admin)
):
    """Create a new entity."""
    db = SessionLocal()
    try:
        # Check if name already exists
        existing = get_entity_by_name(db, name)
        if existing:
            context = get_template_context(
                request,
                error=f"Eine Entität mit dem Namen '{name}' existiert bereits",
                name=name,
                placeholder=placeholder,
                description=description
            )
            return templates.TemplateResponse("entities/create.html", context, status_code=400)

        entity = create_entity(
            db,
            name=name,
            placeholder=placeholder,
            description=description if description else None,
            is_active=is_active
        )
        log_audit(
            db, action="create", summary=f"Entität '{name}' erstellt",
            actor_id=user["id"], actor_username=user["username"],
            target_type="entity", target_id=entity.id, target_label=name,
            ip_address=_client_ip(request),
        )
        return RedirectResponse(url="/admin/entities", status_code=303)
    finally:
        db.close()


@admin_router.get("/entities/{entity_id}/edit", response_class=HTMLResponse)
async def edit_entity_page(
    request: Request,
    entity_id: int,
    user: dict = Depends(require_auth)
):
    """Render the edit entity form."""
    db = SessionLocal()
    try:
        entity = get_entity(db, entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Entität nicht gefunden")

        context = get_template_context(request, entity=entity)
        return templates.TemplateResponse("entities/edit.html", context)
    finally:
        db.close()


@admin_router.post("/entities/{entity_id}/edit")
async def edit_entity_submit(
    request: Request,
    entity_id: int,
    name: Annotated[str, Form()],
    placeholder: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    is_active: Annotated[bool, Form()] = False,
    user: dict = Depends(require_admin)
):
    """Update an entity."""
    db = SessionLocal()
    try:
        entity = get_entity(db, entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Entität nicht gefunden")

        # Check if name already exists (for another entity)
        existing = get_entity_by_name(db, name)
        if existing and existing.id != entity_id:
            context = get_template_context(
                request,
                entity=entity,
                error=f"Eine Entität mit dem Namen '{name}' existiert bereits"
            )
            return templates.TemplateResponse("entities/edit.html", context, status_code=400)

        old_label = entity.name
        update_entity(
            db,
            entity_id,
            name=name,
            placeholder=placeholder,
            description=description if description else None,
            is_active=is_active
        )
        log_audit(
            db, action="update", summary=f"Entität '{old_label}' bearbeitet",
            actor_id=user["id"], actor_username=user["username"],
            target_type="entity", target_id=entity_id, target_label=name,
            ip_address=_client_ip(request),
        )
        return RedirectResponse(url="/admin/entities", status_code=303)
    finally:
        db.close()


@admin_router.post("/entities/{entity_id}/delete")
async def delete_entity_submit(
    request: Request,
    entity_id: int,
    user: dict = Depends(require_admin)
):
    """Delete an entity."""
    db = SessionLocal()
    try:
        entity = get_entity(db, entity_id)
        label = entity.name if entity else str(entity_id)
        delete_entity(db, entity_id)
        log_audit(
            db, action="delete", summary=f"Entität '{label}' gelöscht",
            actor_id=user["id"], actor_username=user["username"],
            target_type="entity", target_id=entity_id, target_label=label,
            ip_address=_client_ip(request),
        )
        return RedirectResponse(url="/admin/entities", status_code=303)
    finally:
        db.close()


# ============================================================================
# Entity detail: patterns + context words hang directly off the entity
# ============================================================================

@admin_router.get("/entities/{entity_id}", response_class=HTMLResponse)
async def view_entity(
    request: Request,
    entity_id: int,
    user: dict = Depends(require_auth)
):
    """Render the entity detail page (patterns + context words)."""
    db = SessionLocal()
    try:
        entity = get_entity(db, entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Entität nicht gefunden")
        context = get_template_context(
            request,
            entity=entity,
            patterns=get_patterns_by_entity(db, entity_id),
            context_words=get_context_words_by_entity(db, entity_id),
            pattern_templates=PATTERN_TEMPLATES,
            sources=_entity_sources(entity, _active_model_entity_sources(db)),
        )
        return templates.TemplateResponse("entities/view.html", context)
    finally:
        db.close()


@admin_router.post("/entities/{entity_id}/patterns/create")
async def create_pattern_submit(
    request: Request,
    entity_id: int,
    name: Annotated[str, Form()],
    regex: Annotated[str, Form()] = "",
    score: Annotated[float, Form()] = 0.5,
    keywords: Annotated[str, Form()] = "",
    user: dict = Depends(require_admin)
):
    """Create a pattern for an entity (raw regex or keyword list).

    In keyword mode the admin enters comma/newline-separated terms and the
    regex is generated here, so no regex knowledge is required. The raw
    regex field stays available for advanced cases.
    """
    db = SessionLocal()
    try:
        entity = get_entity(db, entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Entität nicht gefunden")

        stored_keywords = None
        if keywords.strip():
            regex = build_keyword_regex(keywords)
            stored_keywords = keywords.strip()

        error = _validate_pattern(db, name, regex)
        if error:
            context = get_template_context(
                request, entity=entity,
                patterns=get_patterns_by_entity(db, entity_id),
                context_words=get_context_words_by_entity(db, entity_id),
                error=error,
            )
            return templates.TemplateResponse("entities/view.html", context, status_code=400)

        create_pattern(db, name=name, regex=regex, score=score, entity_id=entity_id, keywords=stored_keywords)
        log_audit(
            db, action="create", summary=f"Muster '{name}' für Entität '{entity.name}' erstellt",
            actor_id=user["id"], actor_username=user["username"],
            target_type="pattern", target_label=name, ip_address=_client_ip(request),
        )
        return RedirectResponse(url=f"/admin/entities/{entity_id}", status_code=303)
    finally:
        db.close()


@admin_router.post("/patterns/{pattern_id}/edit")
async def edit_pattern_submit(
    request: Request,
    pattern_id: int,
    name: Annotated[str, Form()],
    regex: Annotated[str, Form()] = "",
    score: Annotated[float, Form()] = 0.5,
    keywords: Annotated[str, Form()] = "",
    user: dict = Depends(require_admin)
):
    """Update a pattern (raw regex or keyword list)."""
    db = SessionLocal()
    try:
        pattern = get_pattern(db, pattern_id)
        if not pattern:
            raise HTTPException(status_code=404, detail="Muster nicht gefunden")

        stored_keywords = None
        if keywords.strip():
            regex = build_keyword_regex(keywords)
            stored_keywords = keywords.strip()

        error = _validate_pattern(db, name, regex, ignore_id=pattern_id)
        if error:
            context = get_template_context(request, error=error, pattern=pattern)
            return templates.TemplateResponse("patterns/edit.html", context, status_code=400)

        update_pattern(db, pattern_id, name=name, regex=regex, score=score, keywords=stored_keywords)
        log_audit(
            db, action="update", summary=f"Muster '{name}' bearbeitet",
            actor_id=user["id"], actor_username=user["username"],
            target_type="pattern", target_id=pattern_id, target_label=name,
            ip_address=_client_ip(request),
        )
        return RedirectResponse(url=f"/admin/entities/{pattern.entity_id}", status_code=303)
    finally:
        db.close()


@admin_router.get("/patterns/{pattern_id}/edit", response_class=HTMLResponse)
async def edit_pattern_page(
    request: Request,
    pattern_id: int,
    user: dict = Depends(require_auth)
):
    """Render the edit pattern form."""
    db = SessionLocal()
    try:
        pattern = get_pattern(db, pattern_id)
        if not pattern:
            raise HTTPException(status_code=404, detail="Muster nicht gefunden")
        context = get_template_context(request, pattern=pattern)
        return templates.TemplateResponse("patterns/edit.html", context)
    finally:
        db.close()


@admin_router.post("/patterns/{pattern_id}/delete")
async def delete_pattern_submit(
    request: Request,
    pattern_id: int,
    user: dict = Depends(require_admin)
):
    """Delete a pattern."""
    db = SessionLocal()
    try:
        pattern = get_pattern(db, pattern_id)
        if not pattern:
            raise HTTPException(status_code=404, detail="Muster nicht gefunden")
        entity_id = pattern.entity_id
        label = pattern.name
        delete_pattern(db, pattern_id)
        log_audit(
            db, action="delete", summary=f"Muster '{label}' gelöscht",
            actor_id=user["id"], actor_username=user["username"],
            target_type="pattern", target_id=pattern_id, target_label=label,
            ip_address=_client_ip(request),
        )
        return RedirectResponse(url=f"/admin/entities/{entity_id}", status_code=303)
    finally:
        db.close()


@admin_router.post("/entities/{entity_id}/context/create")
async def create_context_word_submit(
    request: Request,
    entity_id: int,
    word: Annotated[str, Form()],
    user: dict = Depends(require_admin)
):
    """Create one or more (comma-separated) context words for an entity."""
    db = SessionLocal()
    try:
        terms = [w.strip() for w in re.split(r"[,\n;]+", word) if w.strip()]
        for term in terms:
            create_context_word(db, word=term, entity_id=entity_id)
        if terms:
            log_audit(
                db, action="create", summary=f"Kontextwörter hinzugefügt: {', '.join(terms)}",
                actor_id=user["id"], actor_username=user["username"],
                target_type="context_word", target_id=entity_id,
                ip_address=_client_ip(request),
            )
        return RedirectResponse(url=f"/admin/entities/{entity_id}", status_code=303)
    finally:
        db.close()


@admin_router.post("/context/{context_word_id}/delete")
async def delete_context_word_submit(
    request: Request,
    context_word_id: int,
    user: dict = Depends(require_admin)
):
    """Delete a context word."""
    db = SessionLocal()
    try:
        context_word = get_context_word(db, context_word_id)
        if not context_word:
            raise HTTPException(status_code=404, detail="Kontextwort nicht gefunden")
        entity_id = context_word.entity_id
        label = context_word.word
        delete_context_word(db, context_word_id)
        log_audit(
            db, action="delete", summary=f"Kontextwort '{label}' gelöscht",
            actor_id=user["id"], actor_username=user["username"],
            target_type="context_word", target_id=context_word_id, target_label=label,
            ip_address=_client_ip(request),
        )
        return RedirectResponse(url=f"/admin/entities/{entity_id}", status_code=303)
    finally:
        db.close()


# ============================================================================
# Transformer models (on/off switches)
# ============================================================================

# Human-readable descriptions for the model cards. Keys are the registry
# keys (= detector_models.name rows) from BERT_MODEL_REGISTRY. The latency
# numbers come from scripts/benchmark_all_models.py (median, 4 CPU cores /
# RTX 3060) - rerun it after changing the registry and update these.
MODEL_DESCRIPTIONS = {
    "transformer_ner_fhswf": {
        "title": "Fließtext-NER (fhswf/bert_de_ner)",
        "description": (
            "Erkennt freie Namen, Orte und Organisationen im Fließtext - auch "
            "ohne umgebende Schlüsselwörter. ~110M Parameter, ~77 ms/Aufruf "
            "(CPU) bzw. ~14 ms (GPU)."
        ),
    },
    "transformer_pii_openmed_small": {
        "title": "PII-Sicherheitsnetz klein (OpenMed PII German 44M)",
        "description": (
            "Zweites Auge für strukturierte personenbezogene Daten: Adressen, "
            "Geburtsdatum, IBAN, E-Mail, Telefon - auch in Format-Varianten, "
            "die die Regex-Muster verpassen. ~44M Parameter, ~111 ms/Aufruf "
            "(CPU) bzw. ~18 ms (GPU)."
        ),
    },
    "transformer_pii_openmed_base": {
        "title": "PII-Sicherheitsnetz mittel (OpenMed PII German 184M)",
        "description": (
            "Wie das kleine Modell, aber genauer (F1 0.963 statt ~0.95). "
            "~184M Parameter, ~167 ms/Aufruf (CPU) bzw. ~27 ms (GPU) - "
            "auf CPU spürbar langsamer, GPU empfohlen."
        ),
    },
    "transformer_pii_openmed_large": {
        "title": "PII-Sicherheitsnetz groß (OpenMed PII German 434M)",
        "description": (
            "Genaueste Variante (F1 0.976). ~434M Parameter, ~680 ms/Aufruf "
            "(CPU) bzw. ~45 ms (GPU) - ohne GPU rund 11x langsamer, daher "
            "nur mit CUDA-GPU sinnvoll."
        ),
    },
}


@admin_router.get("/modelle", response_class=HTMLResponse)
async def list_models(request: Request, user: dict = Depends(require_auth)):
    """Render the transformer model on/off switches."""
    db = SessionLocal()
    try:
        from backend.database.crud import get_detector_model_by_name
        models = []
        for key, entry in BERT_MODEL_REGISTRY.items():
            row = get_detector_model_by_name(db, key)
            meta = MODEL_DESCRIPTIONS.get(key, {"title": key, "description": ""})
            models.append({
                "key": key,
                "title": meta["title"],
                "description": meta["description"],
                "model": entry["model"],
                "is_active": bool(row.is_active) if row else False,
                "entities": ", ".join(sorted(set(entry["mapping"].values()))),
                "gpu_recommended": bool(entry.get("gpu_recommended")),
            })
        context = get_template_context(request, models=models, gpu_available=gpu_available())
        return templates.TemplateResponse("models/list.html", context)
    finally:
        db.close()


@admin_router.post("/modelle/{model_key}/toggle")
async def toggle_model(
    request: Request,
    model_key: str,
    user: dict = Depends(require_admin)
):
    """Toggle a transformer model on or off and rebuild the analyzer.

    Model and label mapping come from BERT_MODEL_REGISTRY in code; the
    admin UI only flips the `detector_models.is_active` flag and reloads,
    mirroring the /api/v1/reload flow.
    """
    if model_key not in BERT_MODEL_REGISTRY:
        raise HTTPException(status_code=404, detail="Modell nicht gefunden")

    db = SessionLocal()
    try:
        from backend.database.crud import get_detector_model_by_name
        row = get_detector_model_by_name(db, model_key)
        new_state = not (row.is_active if row else False)
        set_detector_model_active(db, model_key, new_state)

        # Rebuild the singleton analyzer immediately (same as POST /reload)
        import backend.views.anonymizer as anonymizer_module
        try:
            analyzer = CustomAnalyzer(language="de", db=db)
            anonymizer_module._analyzer = analyzer
            logger.info(f"Analyzer rebuilt after toggling model '{model_key}'")
        except Exception as e:
            logger.error(f"Error rebuilding analyzer after model toggle: {e}")

        log_audit(
            db, action="toggle",
            summary=f"Modell '{model_key}' {'aktiviert' if new_state else 'deaktiviert'}",
            actor_id=user["id"], actor_username=user["username"],
            target_type="detector_model", target_label=model_key,
            ip_address=_client_ip(request),
        )
        return RedirectResponse(url="/admin/modelle", status_code=303)
    finally:
        db.close()


# ============================================================================
# Users (admin-only)
# ============================================================================

@admin_router.get("/users", response_class=HTMLResponse)
async def list_users_page(request: Request, user: dict = Depends(require_admin)):
    """Render the user management page."""
    db = SessionLocal()
    try:
        users = get_admin_users(db)
        context = get_template_context(
            request,
            users=users,
            current_user_id=user["id"],
            valid_roles=VALID_ROLES,
        )
        return templates.TemplateResponse("users/list.html", context)
    finally:
        db.close()


@admin_router.post("/users/create")
async def create_user_submit(
    request: Request,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
    role: Annotated[str, Form()] = "viewer",
    user: dict = Depends(require_admin)
):
    """Create a new admin/viewer user."""
    username = username.strip()
    role = role if role in VALID_ROLES else "viewer"
    db = SessionLocal()
    try:
        def _error(message: str):
            return templates.TemplateResponse(
                "users/list.html",
                get_template_context(
                    request, users=get_admin_users(db), current_user_id=user["id"],
                    valid_roles=VALID_ROLES, error=message,
                ),
                status_code=400,
            )

        if not username:
            return _error("Ein Benutzername ist erforderlich")
        if len(password) < 8:
            return _error("Das Passwort muss mindestens 8 Zeichen lang sein")
        if get_admin_user_by_username(db, username):
            return _error(f"Der Benutzer '{username}' existiert bereits")

        new_user = create_admin_user(db, username=username, password=password, role=role)
        log_audit(
            db, action="create", summary=f"Benutzer '{username}' ({role}) angelegt",
            actor_id=user["id"], actor_username=user["username"],
            target_type="admin_user", target_id=new_user.id, target_label=username,
            ip_address=_client_ip(request),
        )
        return RedirectResponse(url="/admin/users", status_code=303)
    finally:
        db.close()


@admin_router.post("/users/{user_id}/toggle")
async def toggle_user_submit(
    request: Request,
    user_id: int,
    user: dict = Depends(require_admin)
):
    """Activate or deactivate a user (with self/last-admin protection)."""
    db = SessionLocal()
    try:
        target = get_admin_user(db, user_id)
        if not target:
            raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")
        if user_id == user["id"]:
            raise HTTPException(status_code=400, detail="Der eigene Zugang kann nicht deaktiviert werden")

        new_state = not target.is_active
        if not new_state and target.role == "admin" and count_active_admins(db) <= 1:
            raise HTTPException(status_code=400, detail="Der letzte aktive Administrator kann nicht deaktiviert werden")

        set_admin_user_active(db, user_id, new_state)
        log_audit(
            db, action="toggle",
            summary=f"Benutzer '{target.username}' {'aktiviert' if new_state else 'deaktiviert'}",
            actor_id=user["id"], actor_username=user["username"],
            target_type="admin_user", target_id=user_id, target_label=target.username,
            ip_address=_client_ip(request),
        )
        return RedirectResponse(url="/admin/users", status_code=303)
    finally:
        db.close()


@admin_router.post("/users/{user_id}/role")
async def change_user_role_submit(
    request: Request,
    user_id: int,
    role: Annotated[str, Form()],
    user: dict = Depends(require_admin)
):
    """Change a user's role (with self/last-admin protection)."""
    if role not in VALID_ROLES:
        raise HTTPException(status_code=400, detail="Unbekannte Rolle")

    db = SessionLocal()
    try:
        target = get_admin_user(db, user_id)
        if not target:
            raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")
        if user_id == user["id"]:
            raise HTTPException(status_code=400, detail="Die eigene Rolle kann nicht geändert werden")
        if role != "admin" and target.role == "admin" and count_active_admins(db) <= 1:
            raise HTTPException(status_code=400, detail="Der letzte aktive Administrator kann nicht herabgestuft werden")

        update_admin_role(db, user_id, role)
        log_audit(
            db, action="update", summary=f"Rolle von '{target.username}' auf '{role}' geändert",
            actor_id=user["id"], actor_username=user["username"],
            target_type="admin_user", target_id=user_id, target_label=target.username,
            ip_address=_client_ip(request),
        )
        return RedirectResponse(url="/admin/users", status_code=303)
    finally:
        db.close()


@admin_router.post("/users/{user_id}/reset-password")
async def reset_user_password_submit(
    request: Request,
    user_id: int,
    new_password: Annotated[str, Form()],
    user: dict = Depends(require_admin)
):
    """Reset another user's password."""
    db = SessionLocal()
    try:
        target = get_admin_user(db, user_id)
        if not target:
            raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")
        if len(new_password) < 8:
            raise HTTPException(status_code=400, detail="Das Passwort muss mindestens 8 Zeichen lang sein")

        update_admin_password(db, user_id, new_password)
        log_audit(
            db, action="password_change", summary=f"Passwort von '{target.username}' zurückgesetzt",
            actor_id=user["id"], actor_username=user["username"],
            target_type="admin_user", target_id=user_id, target_label=target.username,
            ip_address=_client_ip(request),
        )
        return RedirectResponse(url="/admin/users", status_code=303)
    finally:
        db.close()


@admin_router.post("/users/{user_id}/delete")
async def delete_user_submit(
    request: Request,
    user_id: int,
    user: dict = Depends(require_admin)
):
    """Delete a user (with self/last-admin protection)."""
    db = SessionLocal()
    try:
        target = get_admin_user(db, user_id)
        if not target:
            raise HTTPException(status_code=404, detail="Benutzer nicht gefunden")
        if user_id == user["id"]:
            raise HTTPException(status_code=400, detail="Der eigene Zugang kann nicht gelöscht werden")
        if target.role == "admin" and count_active_admins(db) <= 1:
            raise HTTPException(status_code=400, detail="Der letzte aktive Administrator kann nicht gelöscht werden")

        label = target.username
        delete_admin_user(db, user_id)
        log_audit(
            db, action="delete", summary=f"Benutzer '{label}' gelöscht",
            actor_id=user["id"], actor_username=user["username"],
            target_type="admin_user", target_id=user_id, target_label=label,
            ip_address=_client_ip(request),
        )
        return RedirectResponse(url="/admin/users", status_code=303)
    finally:
        db.close()


# ============================================================================
# Audit log (admin-only)
# ============================================================================

PAGE_SIZE = 100


@admin_router.get("/audit", response_class=HTMLResponse)
async def audit_page(request: Request, user: dict = Depends(require_admin)):
    """Render the read-only audit log with simple filters."""
    db = SessionLocal()
    try:
        actor = request.query_params.get("actor") or None
        action = request.query_params.get("action") or None
        target_type = request.query_params.get("target_type") or None
        page = max(1, int(request.query_params.get("page", 1)))
        total = count_audit_logs(db, actor_username=actor, action=action, target_type=target_type)
        entries = get_audit_logs(
            db, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE,
            actor_username=actor, action=action, target_type=target_type,
        )
        context = get_template_context(
            request,
            entries=entries,
            total=total,
            page=page,
            page_size=PAGE_SIZE,
            total_pages=max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
            filter_actor=actor or "",
            filter_action=action or "",
            filter_target_type=target_type or "",
        )
        return templates.TemplateResponse("audit/list.html", context)
    finally:
        db.close()


# ============================================================================
# Request traces (admin-only, content-free)
# ============================================================================

@admin_router.get("/traces", response_class=HTMLResponse)
async def traces_page(request: Request, user: dict = Depends(require_admin)):
    """Render the read-only request traces (metadata only)."""
    db = SessionLocal()
    try:
        source = request.query_params.get("source") or None
        page = max(1, int(request.query_params.get("page", 1)))
        total = count_request_traces(db, source=source)
        rows = get_request_traces(db, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE, source=source)

        # Parse the JSON entity counts for display.
        traces = []
        for row in rows:
            try:
                counts = json.loads(row.entity_counts) if row.entity_counts else {}
            except (ValueError, TypeError):
                counts = {}
            traces.append({"row": row, "counts": counts})

        context = get_template_context(
            request,
            traces=traces,
            total=total,
            page=page,
            page_size=PAGE_SIZE,
            total_pages=max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
            filter_source=source or "",
            trace_enabled=TRACE_ENABLED,
            retention_days=TRACE_RETENTION_DAYS,
        )
        return templates.TemplateResponse("traces/list.html", context)
    finally:
        db.close()