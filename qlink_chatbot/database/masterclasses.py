"""Dashboard-managed masterclasses (exactly one Active for WhatsApp)."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from qlink_chatbot.database.collections import masterclasses
from qlink_chatbot.utils.logger_config import logger


def _serialize(doc: dict) -> dict:
    doc = dict(doc)
    doc.pop("_id", None)
    for field in ("created_at", "updated_at"):
        value = doc.get(field)
        if isinstance(value, datetime):
            doc[field] = value.isoformat()
    return doc


def list_masterclasses() -> list[dict]:
    docs = list(masterclasses.find({}).sort([("is_active", -1), ("updated_at", -1)]))
    return [_serialize(doc) for doc in docs]


def get_masterclass(masterclass_id: str) -> dict | None:
    if not masterclass_id:
        return None
    doc = masterclasses.find_one({"masterclass_id": masterclass_id})
    return _serialize(doc) if doc else None


def get_active_masterclass() -> dict | None:
    doc = masterclasses.find_one({"is_active": True})
    return _serialize(doc) if doc else None


def create_masterclass(
    title: str,
    meeting_link: str,
    notes: str | None = None,
    activate: bool = False,
) -> dict:
    now = datetime.now(timezone.utc)
    masterclass_id = str(uuid4())
    doc = {
        "masterclass_id": masterclass_id,
        "title": title.strip(),
        "meeting_link": meeting_link.strip(),
        "notes": (notes or "").strip() or None,
        "is_active": False,
        "created_at": now,
        "updated_at": now,
    }
    masterclasses.insert_one(doc)
    if activate:
        set_active(masterclass_id)
        return get_masterclass(masterclass_id)
    logger.info("Masterclass created", extra={"masterclass_id": masterclass_id})
    return _serialize(doc)


def update_masterclass(
    masterclass_id: str,
    *,
    title: str | None = None,
    meeting_link: str | None = None,
    notes: str | None = None,
) -> dict | None:
    existing = masterclasses.find_one({"masterclass_id": masterclass_id})
    if not existing:
        return None
    fields: dict = {"updated_at": datetime.now(timezone.utc)}
    if title is not None:
        fields["title"] = title.strip()
    if meeting_link is not None:
        fields["meeting_link"] = meeting_link.strip()
    if notes is not None:
        fields["notes"] = notes.strip() or None
    masterclasses.update_one({"masterclass_id": masterclass_id}, {"$set": fields})
    return get_masterclass(masterclass_id)


def set_active(masterclass_id: str) -> dict | None:
    existing = masterclasses.find_one({"masterclass_id": masterclass_id})
    if not existing:
        return None
    now = datetime.now(timezone.utc)
    masterclasses.update_many({}, {"$set": {"is_active": False, "updated_at": now}})
    masterclasses.update_one(
        {"masterclass_id": masterclass_id},
        {"$set": {"is_active": True, "updated_at": now}},
    )
    logger.info("Masterclass activated", extra={"masterclass_id": masterclass_id})
    return get_masterclass(masterclass_id)


def deactivate_all() -> int:
    now = datetime.now(timezone.utc)
    result = masterclasses.update_many(
        {"is_active": True},
        {"$set": {"is_active": False, "updated_at": now}},
    )
    return result.modified_count


def delete_masterclass(masterclass_id: str) -> tuple[bool, str]:
    existing = masterclasses.find_one({"masterclass_id": masterclass_id})
    if not existing:
        return False, "Masterclass not found"
    if existing.get("is_active"):
        return False, "Deactivate this masterclass before deleting it"
    masterclasses.delete_one({"masterclass_id": masterclass_id})
    return True, "Deleted"


def build_masterclass_reply(mc: dict) -> str:
    title = (mc.get("title") or "the masterclass").strip()
    link = (mc.get("meeting_link") or "").strip()
    return f"Here's the link for {title}: {link}"
