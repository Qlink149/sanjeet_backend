"""Dashboard CRUD for /go/<slug> short links (see database/short_links.py).

Auth: matches the other /dashboard endpoints, which have no server-side auth
(the dashboard login only gates the UI). Do not treat these as private.
"""

import asyncio
import os

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from qlink_chatbot.database.short_links import (
    delete_short_link,
    get_short_link,
    list_short_links,
    normalize_slug,
    upsert_short_link,
    validate_target,
)
from qlink_chatbot.utils.logger_config import logger

link_router = APIRouter()

DEFAULT_PUBLIC_URL = "https://sanjeet.ray.claraai.tech"


class LinkCreate(BaseModel):
    slug: str
    target: str
    note: str | None = ""


class LinkUpdate(BaseModel):
    target: str | None = None
    note: str | None = None


def _public_url(slug: str) -> str:
    base = (os.environ.get("DASHBOARD_PUBLIC_URL") or DEFAULT_PUBLIC_URL).rstrip("/")
    return f"{base}/go/{slug}"


def _serialize(link: dict) -> dict:
    out = {
        "slug": link.get("slug"),
        "target": link.get("target", ""),
        "note": link.get("note") or "",
        "clicks": link.get("clicks", 0),
        "public_url": _public_url(link.get("slug", "")),
    }
    for key in ("created_at", "updated_at", "last_clicked_at"):
        value = link.get(key)
        out[key] = value.isoformat() if hasattr(value, "isoformat") else value
    return out


def _error(message: str, status: int) -> JSONResponse:
    return JSONResponse({"success": False, "message": message}, status_code=status)


@link_router.get("/links")
async def fetch_links():
    try:
        rows = await asyncio.to_thread(list_short_links)
        return {"success": True, "data": [_serialize(r) for r in rows]}
    except Exception:
        logger.exception("Error listing short links")
        return _error("Error listing links", 500)


@link_router.post("/links")
async def create_link(body: LinkCreate):
    try:
        slug = normalize_slug(body.slug)
        validate_target(body.target)
    except ValueError as exc:
        return _error(str(exc), 400)
    try:
        if await asyncio.to_thread(get_short_link, slug):
            return _error(f"A link named '{slug}' already exists", 409)
        await asyncio.to_thread(
            upsert_short_link, slug, body.target, (body.note or "").strip()
        )
        link = await asyncio.to_thread(get_short_link, slug)
        return JSONResponse(
            {
                "success": True,
                "data": _serialize(link or {"slug": slug, "target": body.target}),
            },
            status_code=201,
        )
    except Exception:
        logger.exception("Error creating short link")
        return _error("Error creating link", 500)


@link_router.patch("/links/{slug}")
async def update_link(slug: str, body: LinkUpdate):
    try:
        slug = normalize_slug(slug)
        if body.target is not None:
            validate_target(body.target)
    except ValueError as exc:
        return _error(str(exc), 400)
    try:
        existing = await asyncio.to_thread(get_short_link, slug)
        if not existing:
            return _error("Link not found", 404)
        target = body.target if body.target is not None else existing.get("target", "")
        note = (
            (body.note or "").strip()
            if body.note is not None
            else existing.get("note", "")
        )
        await asyncio.to_thread(upsert_short_link, slug, target, note)
        link = await asyncio.to_thread(get_short_link, slug)
        return {"success": True, "data": _serialize(link or existing)}
    except Exception:
        logger.exception("Error updating short link")
        return _error("Error updating link", 500)


@link_router.delete("/links/{slug}")
async def remove_link(slug: str):
    try:
        slug = normalize_slug(slug)
    except ValueError as exc:
        return _error(str(exc), 400)
    try:
        if not await asyncio.to_thread(delete_short_link, slug):
            return _error("Link not found", 404)
        return {"success": True}
    except Exception:
        logger.exception("Error deleting short link")
        return _error("Error deleting link", 500)
