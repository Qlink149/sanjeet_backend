"""Public /go/<slug> redirects (see database/short_links.py)."""

import asyncio
import re

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, RedirectResponse

from qlink_chatbot.database.masterclasses import get_active_masterclass
from qlink_chatbot.database.short_links import (
    MASTERCLASS_TARGET,
    get_short_link,
    record_click,
)
from qlink_chatbot.utils.logger_config import logger

short_link_router = APIRouter()


def _active_masterclass_link(mc: dict | None) -> str:
    """Joining URL: the structured field, else the first URL in the free-text message."""
    if not mc:
        return ""
    url = (mc.get("meeting_url") or "").strip()
    if url:
        return url
    match = re.search(r"https?://\S+", mc.get("meeting_link") or "")
    return match.group(0) if match else ""

_NOT_FOUND = (
    "<h3 style='font-family:sans-serif'>This link is not available. "
    "Please check back later.</h3>"
)


@short_link_router.get("/go/{slug}")
async def go(slug: str):
    link = await asyncio.to_thread(get_short_link, slug)
    if not link:
        return HTMLResponse(_NOT_FOUND, status_code=404)

    target = link.get("target") or ""
    if target == MASTERCLASS_TARGET:
        active = await asyncio.to_thread(get_active_masterclass)
        target = _active_masterclass_link(active)
        if not target:
            return HTMLResponse(
                "<h3 style='font-family:sans-serif'>The masterclass link is not "
                "live yet. Please check back closer to the start time.</h3>",
                status_code=404,
            )

    try:
        await asyncio.to_thread(record_click, link["slug"])
    except Exception as exc:  # a stats failure must never block the redirect
        logger.warning("short link click not recorded", extra={"error": str(exc)})
    return RedirectResponse(target, status_code=302)
