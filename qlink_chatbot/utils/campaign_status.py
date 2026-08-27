"""Helpers for campaign delivery-status webhook handling."""

STATUS_RANK = {
    "pending": 0,
    "enqueued": 1,
    "sent": 2,
    "delivered": 3,
    "read": 4,
    "failed": 5,
    "undelivered": 5,
}

_TERMINAL = frozenset({"failed", "undelivered"})


def extract_status_lookup_ids(
    status_obj: dict,
) -> tuple[str | None, str | None]:
    """Extract (primary_id, whatsapp_message_id) from a status webhook object.

    Gupshup passthrough V3 statuses carry:
    - ``gs_id``: Gupshup message id (same as submit-response ``messageId``)
    - ``id``: WhatsApp message id (different UUID)

    We store ``messageId`` / ``gs_id`` at send time, so primary lookup must
    prefer ``gs_id``.
    """
    gs_id = status_obj.get("gs_id") or status_obj.get("gsId")
    wa_id = status_obj.get("id") or status_obj.get("meta_msg_id")
    if gs_id:
        return gs_id, wa_id
    return wa_id, None


def extract_message_event_ids(
    payload: dict,
) -> tuple[str | None, str | None]:
    """Extract lookup ids from a native Gupshup ``message-event`` payload.

    In that format ``id`` is typically the Gupshup message id. Prefer an
    explicit ``gsId`` / ``gs_id`` when present.
    """
    gs_id = payload.get("gsId") or payload.get("gs_id")
    event_id = payload.get("id")
    if gs_id:
        wa_id = event_id if event_id and event_id != gs_id else None
        return gs_id, wa_id
    return event_id, None


def extract_v3_failure_reason(event_payload: dict) -> str | None:
    """Pull the human-readable rejection reason from a Gupshup V3 failed event.

    Shape: ``{"type": "failed", "payload": {"code": 470, "reason": "..."}}``.
    The nested ``payload`` key is a different dict from the outer event
    payload and holds only the failure detail.
    """
    detail = event_payload.get("payload") or {}
    reason = detail.get("reason")
    code = detail.get("code")
    if reason and code:
        return f"[{code}] {reason}"
    return reason or (str(code) if code else None)


def extract_meta_failure_reason(status_obj: dict) -> str | None:
    """Pull the rejection reason from a Meta Cloud API status ``errors`` array.

    Example: ``{"errors": [{"code": ..., "title": "..."}]}``.
    """
    errors = status_obj.get("errors") or []
    if not errors:
        return None
    first = errors[0]
    title = first.get("title") or first.get("message")
    code = first.get("code")
    if title and code:
        return f"[{code}] {title}"
    return title or (str(code) if code else None)


def should_apply_status(current: str | None, new: str) -> bool:
    """Return True if ``new`` should replace ``current`` (no downgrades).

    ``failed`` / ``undelivered`` are terminal. Other statuses only move
    forward by rank.
    """
    if not new:
        return False
    current = current or "pending"
    if current in _TERMINAL:
        return False
    if new in _TERMINAL:
        return True
    return STATUS_RANK.get(new, -1) >= STATUS_RANK.get(current, -1)
