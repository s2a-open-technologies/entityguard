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

import logging
import re
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from backend.components.bert_recognizer import BERT_MODEL_REGISTRY, gpu_available
from backend.components.cstm_analyzer import CustomAnalyzer
from backend.database import SessionLocal
from backend.database.crud import (
    create_allowed_value, create_context_word, create_entity, create_pattern,
    delete_allowed_value, delete_context_word, delete_entity, delete_pattern,
    get_admin_user, get_allowed_values, get_allowed_value_by_value, get_context_word,
    get_context_words_by_entity, get_entities, get_entity, get_entity_by_name, get_pattern,
    get_pattern_by_name, get_patterns_by_entity, set_detector_model_active,
    update_admin_password, update_entity, update_pattern, verify_password,
)

from .auth import authenticate_user, create_session, delete_session, require_auth, SESSION_COOKIE_NAME
from .dependencies import get_template_context

# Router
admin_router = APIRouter(prefix="/admin", tags=["Admin"])

# Logger
logger = logging.getLogger("uvicorn.error")

# Templates
TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "frontend" / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)


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
        context = get_template_context(request, error="Ungültiger Benutzername oder ungültiges Passwort")
        return templates.TemplateResponse("login.html", context, status_code=401)

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
    user: dict = Depends(require_auth)
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
        return RedirectResponse(url="/admin/allowlist", status_code=303)
    finally:
        db.close()


@admin_router.post("/allowlist/{allowed_value_id}/delete")
async def delete_allowed_value_submit(
    request: Request,
    allowed_value_id: int,
    user: dict = Depends(require_auth)
):
    """Delete an allow-listed value."""
    db = SessionLocal()
    try:
        delete_allowed_value(db, allowed_value_id)
        return RedirectResponse(url="/admin/allowlist", status_code=303)
    finally:
        db.close()


# ============================================================================
# Entities
# ============================================================================

@admin_router.get("/entities", response_class=HTMLResponse)
async def list_entities(request: Request, user: dict = Depends(require_auth)):
    """Render the list of entities."""
    db = SessionLocal()
    try:
        entities = get_entities(db)
        pattern_counts = {e.id: len(e.patterns) for e in entities}
        context = get_template_context(
            request, entities=entities, pattern_counts=pattern_counts
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
    user: dict = Depends(require_auth)
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

        create_entity(
            db,
            name=name,
            placeholder=placeholder,
            description=description if description else None,
            is_active=is_active
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
    user: dict = Depends(require_auth)
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

        update_entity(
            db,
            entity_id,
            name=name,
            placeholder=placeholder,
            description=description if description else None,
            is_active=is_active
        )
        return RedirectResponse(url="/admin/entities", status_code=303)
    finally:
        db.close()


@admin_router.post("/entities/{entity_id}/delete")
async def delete_entity_submit(
    request: Request,
    entity_id: int,
    user: dict = Depends(require_auth)
):
    """Delete an entity."""
    db = SessionLocal()
    try:
        delete_entity(db, entity_id)
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
    user: dict = Depends(require_auth)
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
    user: dict = Depends(require_auth)
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
    user: dict = Depends(require_auth)
):
    """Delete a pattern."""
    db = SessionLocal()
    try:
        pattern = get_pattern(db, pattern_id)
        if not pattern:
            raise HTTPException(status_code=404, detail="Muster nicht gefunden")
        entity_id = pattern.entity_id
        delete_pattern(db, pattern_id)
        return RedirectResponse(url=f"/admin/entities/{entity_id}", status_code=303)
    finally:
        db.close()


@admin_router.post("/entities/{entity_id}/context/create")
async def create_context_word_submit(
    request: Request,
    entity_id: int,
    word: Annotated[str, Form()],
    user: dict = Depends(require_auth)
):
    """Create one or more (comma-separated) context words for an entity."""
    db = SessionLocal()
    try:
        for term in [w.strip() for w in re.split(r"[,\n;]+", word) if w.strip()]:
            create_context_word(db, word=term, entity_id=entity_id)
        return RedirectResponse(url=f"/admin/entities/{entity_id}", status_code=303)
    finally:
        db.close()


@admin_router.post("/context/{context_word_id}/delete")
async def delete_context_word_submit(
    request: Request,
    context_word_id: int,
    user: dict = Depends(require_auth)
):
    """Delete a context word."""
    db = SessionLocal()
    try:
        context_word = get_context_word(db, context_word_id)
        if not context_word:
            raise HTTPException(status_code=404, detail="Kontextwort nicht gefunden")
        entity_id = context_word.entity_id
        delete_context_word(db, context_word_id)
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
    user: dict = Depends(require_auth)
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

        return RedirectResponse(url="/admin/modelle", status_code=303)
    finally:
        db.close()