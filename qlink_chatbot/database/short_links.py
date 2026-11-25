"""Named redirect links served at /go/<slug> (e.g. https://<dashboard>/go/coterie).

WhatsApp template buttons are re-approved on every edit and Meta rejects buttons
that point straight at chat.whatsapp.com. Templates therefore carry a stable
``/go/<slug>`` URL on our own domain and the target lives here, so a link can be
added or changed without a new template or a deploy.

Targets are only ever set by the team (script / dashboard), never from the
request, so the route cannot be used as an open redirect.
"""

import re
from datetime import datetime, timezone

from qlink_chatbot.database.database import db

short_links = db["short_links"]

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
# Target that resolves to the Active masterclass's joining link at click time.
MASTERCLASS_TARGET = "@masterclass"


def normalize_slug(slug: str) -> str:
    slug = (slug or "").strip().lower()
    if not SLUG_RE.match(slug):
        raise ValueError(
            "slug must be 1-40 chars: lowercase letters, digits, '-' or '_'"
        )
    return slug


def validate_target(target: str) -> str:
    target = (target or "").strip()
    if target == MASTERCLASS_TARGET:
        return target
    if not re.match(r"^https://[^\s]+$", target):
        raise ValueError("target must be an https:// URL or '@masterclass'")
    return target


def get_short_link(slug: str) -> dict | None:
    try:
        slug = normalize_slug(slug)
    except ValueError:
        return None
    return short_links.find_one({"slug": slug}, {"_id": 0})


def record_click(slug: str) -> None:
    short_links.update_one(
        {"slug": slug},
        {
            "$inc": {"clicks": 1},
            "$set": {"last_clicked_at": datetime.now(timezone.utc)},
        },
    )


def upsert_short_link(slug: str, target: str, note: str = "") -> dict:
    slug = normalize_slug(slug)
    target = validate_target(target)
    now = datetime.now(timezone.utc)
    short_links.update_one(
        {"slug": slug},
        {
            "$set": {"target": target, "note": note, "updated_at": now},
            "$setOnInsert": {"slug": slug, "created_at": now, "clicks": 0},
        },
        upsert=True,
    )
    return {"slug": slug, "target": target, "note": note}


def delete_short_link(slug: str) -> bool:
    return short_links.delete_one({"slug": normalize_slug(slug)}).deleted_count > 0


def list_short_links() -> list[dict]:
    return list(short_links.find({}, {"_id": 0}).sort("slug", 1))
