"""Resolve public header image URLs for template sends."""

from qlink_chatbot.database.db_utils import get_template_image
from qlink_chatbot.utils.env_load import public_base_url


def resolve_template_image_url(template_id: str) -> str | None:
    """Return the public image URL for a template header, if one exists."""
    base = (public_base_url or "").rstrip("/")
    if not base or not template_id:
        return None
    if get_template_image(template_id) is None:
        return None
    return f"{base}/dashboard/template-image/{template_id}"
