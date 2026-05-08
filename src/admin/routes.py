"""
Admin interface routes.

This module provides all routes for the admin interface including
authentication, dashboard, and CRUD operations for recognizers and patterns.
"""

import re
from typing import Annotated
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from src.database import SessionLocal
from src.database.crud import (
    get_recognizer, get_recognizers, create_recognizer, update_recognizer, delete_recognizer,
    get_pattern, get_patterns_by_recognizer, create_pattern, update_pattern, delete_pattern,
    get_context_words_by_recognizer, create_context_word, delete_context_word,
    get_admin_user, update_admin_password,
    get_entities, get_entity, get_entity_by_name, create_entity, update_entity, delete_entity
)
from .auth import (
    create_session, delete_session, require_auth, SESSION_COOKIE_NAME,
    authenticate_user
)
from .dependencies import get_template_context

# Router
admin_router = APIRouter(prefix="/admin", tags=["Admin"])

# Templates
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)


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
        context = get_template_context(request, error="Invalid username or password")
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
        recognizers = get_recognizers(db)
        active_count = sum(1 for r in recognizers if r.is_active)
        total_patterns = sum(len(r.patterns) for r in recognizers)
        context = get_template_context(
            request,
            recognizers=recognizers,
            active_count=active_count,
            total_patterns=total_patterns
        )
        return templates.TemplateResponse("dashboard.html", context)
    finally:
        db.close()


# ============================================================================
# Recognizers
# ============================================================================

@admin_router.get("/recognizers", response_class=HTMLResponse)
async def list_recognizers(request: Request, user: dict = Depends(require_auth)):
    """Render the list of recognizers."""
    db = SessionLocal()
    try:
        recognizers = get_recognizers(db)
        context = get_template_context(request, recognizers=recognizers)
        return templates.TemplateResponse("recognizers/list.html", context)
    finally:
        db.close()


@admin_router.get("/recognizers/create", response_class=HTMLResponse)
async def create_recognizer_page(request: Request, user: dict = Depends(require_auth)):
    """Render the create recognizer form."""
    db = SessionLocal()
    try:
        entities = get_entities(db, active_only=True)
        context = get_template_context(request, entities=entities)
        return templates.TemplateResponse("recognizers/create.html", context)
    finally:
        db.close()


@admin_router.post("/recognizers/create")
async def create_recognizer_submit(
    request: Request,
    name: Annotated[str, Form()],
    supported_entity: Annotated[str, Form()],
    supported_language: Annotated[str, Form()] = "de",
    is_active: Annotated[bool, Form()] = True,
    user: dict = Depends(require_auth)
):
    """Create a new recognizer."""
    db = SessionLocal()
    try:
        # Check if name already exists
        existing = get_recognizer_by_name_internal(db, name)
        if existing:
            entities = get_entities(db, active_only=True)
            context = get_template_context(
                request,
                entities=entities,
                error=f"Recognizer with name '{name}' already exists",
                name=name,
                supported_entity=supported_entity,
                supported_language=supported_language
            )
            return templates.TemplateResponse("recognizers/create.html", context, status_code=400)

        recognizer = create_recognizer(
            db,
            name=name,
            supported_entity=supported_entity,
            supported_language=supported_language,
            is_active=is_active
        )
        return RedirectResponse(url=f"/admin/recognizers/{recognizer.id}", status_code=303)
    finally:
        db.close()


@admin_router.get("/recognizers/{recognizer_id}", response_class=HTMLResponse)
async def view_recognizer(
    request: Request,
    recognizer_id: int,
    user: dict = Depends(require_auth)
):
    """Render the recognizer detail page."""
    db = SessionLocal()
    try:
        recognizer = get_recognizer(db, recognizer_id)
        if not recognizer:
            raise HTTPException(status_code=404, detail="Recognizer not found")

        patterns = get_patterns_by_recognizer(db, recognizer_id)
        context_words = get_context_words_by_recognizer(db, recognizer_id)

        context = get_template_context(
            request,
            recognizer=recognizer,
            patterns=patterns,
            context_words=context_words
        )
        return templates.TemplateResponse("recognizers/view.html", context)
    finally:
        db.close()


@admin_router.get("/recognizers/{recognizer_id}/edit", response_class=HTMLResponse)
async def edit_recognizer_page(
    request: Request,
    recognizer_id: int,
    user: dict = Depends(require_auth)
):
    """Render the edit recognizer form."""
    db = SessionLocal()
    try:
        recognizer = get_recognizer(db, recognizer_id)
        if not recognizer:
            raise HTTPException(status_code=404, detail="Recognizer not found")

        entities = get_entities(db, active_only=True)
        context = get_template_context(request, recognizer=recognizer, entities=entities)
        return templates.TemplateResponse("recognizers/edit.html", context)
    finally:
        db.close()


@admin_router.post("/recognizers/{recognizer_id}/edit")
async def edit_recognizer_submit(
    request: Request,
    recognizer_id: int,
    name: Annotated[str, Form()],
    supported_entity: Annotated[str, Form()],
    supported_language: Annotated[str, Form()] = "de",
    is_active: Annotated[bool, Form()] = False,
    user: dict = Depends(require_auth)
):
    """Update a recognizer."""
    db = SessionLocal()
    try:
        recognizer = get_recognizer(db, recognizer_id)
        if not recognizer:
            raise HTTPException(status_code=404, detail="Recognizer not found")

        # Check if name already exists (for another recognizer)
        existing = get_recognizer_by_name_internal(db, name)
        if existing and existing.id != recognizer_id:
            entities = get_entities(db, active_only=True)
            context = get_template_context(
                request,
                recognizer=recognizer,
                entities=entities,
                error=f"Recognizer with name '{name}' already exists"
            )
            return templates.TemplateResponse("recognizers/edit.html", context, status_code=400)

        update_recognizer(
            db,
            recognizer_id,
            name=name,
            supported_entity=supported_entity,
            supported_language=supported_language,
            is_active=is_active
        )
        return RedirectResponse(url=f"/admin/recognizers/{recognizer_id}", status_code=303)
    finally:
        db.close()


@admin_router.post("/recognizers/{recognizer_id}/delete")
async def delete_recognizer_submit(
    request: Request,
    recognizer_id: int,
    user: dict = Depends(require_auth)
):
    """Delete a recognizer."""
    db = SessionLocal()
    try:
        delete_recognizer(db, recognizer_id)
        return RedirectResponse(url="/admin/recognizers", status_code=303)
    finally:
        db.close()


# ============================================================================
# Patterns
# ============================================================================

@admin_router.post("/recognizers/{recognizer_id}/patterns/create")
async def create_pattern_submit(
    request: Request,
    recognizer_id: int,
    name: Annotated[str, Form()],
    regex: Annotated[str, Form()],
    score: Annotated[float, Form()],
    user: dict = Depends(require_auth)
):
    """Create a new pattern for a recognizer."""
    db = SessionLocal()
    try:
        # Validate regex
        try:
            re.compile(regex)
        except re.error as e:
            recognizer = get_recognizer(db, recognizer_id)
            patterns = get_patterns_by_recognizer(db, recognizer_id)
            context_words = get_context_words_by_recognizer(db, recognizer_id)
            context = get_template_context(
                request,
                recognizer=recognizer,
                patterns=patterns,
                context_words=context_words,
                error=f"Invalid regex: {str(e)}",
                pattern_name=name,
                pattern_regex=regex,
                pattern_score=score
            )
            return templates.TemplateResponse("recognizers/view.html", context, status_code=400)

        # Check if name already exists
        existing = get_pattern_by_name_internal(db, name)
        if existing:
            recognizer = get_recognizer(db, recognizer_id)
            patterns = get_patterns_by_recognizer(db, recognizer_id)
            context_words = get_context_words_by_recognizer(db, recognizer_id)
            context = get_template_context(
                request,
                recognizer=recognizer,
                patterns=patterns,
                context_words=context_words,
                error=f"Pattern with name '{name}' already exists"
            )
            return templates.TemplateResponse("recognizers/view.html", context, status_code=400)

        create_pattern(db, name=name, regex=regex, score=score, recognizer_id=recognizer_id)
        return RedirectResponse(url=f"/admin/recognizers/{recognizer_id}", status_code=303)
    finally:
        db.close()


@admin_router.post("/patterns/{pattern_id}/edit")
async def edit_pattern_submit(
    request: Request,
    pattern_id: int,
    name: Annotated[str, Form()],
    regex: Annotated[str, Form()],
    score: Annotated[float, Form()],
    user: dict = Depends(require_auth)
):
    """Update a pattern."""
    db = SessionLocal()
    try:
        pattern = get_pattern(db, pattern_id)
        if not pattern:
            raise HTTPException(status_code=404, detail="Pattern not found")

        # Validate regex
        try:
            re.compile(regex)
        except re.error as e:
            context = get_template_context(
                request,
                error=f"Invalid regex: {str(e)}",
                pattern=pattern
            )
            return templates.TemplateResponse("patterns/edit.html", context, status_code=400)

        update_pattern(db, pattern_id, name=name, regex=regex, score=score)
        return RedirectResponse(url=f"/admin/recognizers/{pattern.recognizer_id}", status_code=303)
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
            raise HTTPException(status_code=404, detail="Pattern not found")

        recognizer_id = pattern.recognizer_id
        delete_pattern(db, pattern_id)
        return RedirectResponse(url=f"/admin/recognizers/{recognizer_id}", status_code=303)
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
            raise HTTPException(status_code=404, detail="Pattern not found")

        context = get_template_context(request, pattern=pattern)
        return templates.TemplateResponse("patterns/edit.html", context)
    finally:
        db.close()


# ============================================================================
# Context Words
# ============================================================================

@admin_router.post("/recognizers/{recognizer_id}/context/create")
async def create_context_word_submit(
    request: Request,
    recognizer_id: int,
    word: Annotated[str, Form()],
    user: dict = Depends(require_auth)
):
    """Create a new context word for a recognizer."""
    db = SessionLocal()
    try:
        create_context_word(db, word=word, recognizer_id=recognizer_id)
        return RedirectResponse(url=f"/admin/recognizers/{recognizer_id}", status_code=303)
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
        context_word = get_context_word_internal(db, context_word_id)
        if not context_word:
            raise HTTPException(status_code=404, detail="Context word not found")

        recognizer_id = context_word.recognizer_id
        delete_context_word(db, context_word_id)
        return RedirectResponse(url=f"/admin/recognizers/{recognizer_id}", status_code=303)
    finally:
        db.close()


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
            raise HTTPException(status_code=404, detail="User not found")

        from src.database.crud import verify_password
        if not verify_password(current_password, db_user.password_hash):
            context = get_template_context(request, error="Current password is incorrect")
            return templates.TemplateResponse("profile/password.html", context, status_code=400)

        # Validate new password
        if len(new_password) < 8:
            context = get_template_context(request, error="Password must be at least 8 characters")
            return templates.TemplateResponse("profile/password.html", context, status_code=400)

        if new_password != confirm_password:
            context = get_template_context(request, error="Passwords do not match")
            return templates.TemplateResponse("profile/password.html", context, status_code=400)

        # Update password
        update_admin_password(db, user["id"], new_password)

        context = get_template_context(request, success="Password changed successfully")
        return templates.TemplateResponse("profile/password.html", context)
    finally:
        db.close()


# ============================================================================
# Pattern Preview (API)
# ============================================================================

@admin_router.post("/preview")
async def preview_pattern(
    request: Request,
    text: Annotated[str, Form()],
    pattern: Annotated[str, Form()],
    user: dict = Depends(require_auth)
):
    """Preview how a pattern matches text."""
    try:
        compiled_pattern = re.compile(pattern)
        matches = list(compiled_pattern.finditer(text))
        return {
            "success": True,
            "matches": [
                {"start": m.start(), "end": m.end(), "match": m.group()}
                for m in matches
            ]
        }
    except re.error as e:
        return {"success": False, "error": str(e)}


# ============================================================================
# Helper functions
# ============================================================================

def get_recognizer_by_name_internal(db, name: str):
    """Internal helper to get recognizer by name."""
    from src.database.crud import get_recognizer_by_name
    return get_recognizer_by_name(db, name)


def get_pattern_by_name_internal(db, name: str):
    """Internal helper to get pattern by name."""
    from src.database.crud import get_pattern_by_name
    return get_pattern_by_name(db, name)


def get_context_word_internal(db, context_word_id: int):
    """Internal helper to get context word."""
    from src.database.crud import get_context_word
    return get_context_word(db, context_word_id)


# ============================================================================
# Entities
# ============================================================================

@admin_router.get("/entities", response_class=HTMLResponse)
async def list_entities(request: Request, user: dict = Depends(require_auth)):
    """Render the list of entities."""
    db = SessionLocal()
    try:
        entities = get_entities(db)
        context = get_template_context(request, entities=entities)
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
                error=f"Entity with name '{name}' already exists",
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
            raise HTTPException(status_code=404, detail="Entity not found")

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
            raise HTTPException(status_code=404, detail="Entity not found")

        # Check if name already exists (for another entity)
        existing = get_entity_by_name(db, name)
        if existing and existing.id != entity_id:
            context = get_template_context(
                request,
                entity=entity,
                error=f"Entity with name '{name}' already exists"
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