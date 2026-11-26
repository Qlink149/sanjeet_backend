"""Values for the {{n}} variables of templates sent as dashboard broadcasts.

A campaign or schedule stores ``template_params``: one item per {{n}}, in order.
An item is either literal text, or ``{"token": "first_name" | "name",
"fallback": "there"}``, which is filled from each recipient's lead record.

Nothing is sent unless the number of items matches the template exactly.
"""

from __future__ import annotations

import json
import re
import unicodedata

from qlink_chatbot.database.leads import find_lead_by_phone
from qlink_chatbot.utils.logger_config import logger

NAME_TOKENS = ("first_name", "name")
DEFAULT_FALLBACK = "there"

_VARIABLE_RE = re.compile(r"\{\{\s*([^{}]*?)\s*\}\}")
_WHOLE_TOKEN_RE = re.compile(r"^\{([a-z_]+)\}$")
_EMBEDDED_TOKEN_RE = re.compile(r"\{(first_name|name)\}")
# Name given to leads we only know by number, e.g. "WhatsApp 1234".
_AUTO_NAME_RE = re.compile(r"^whatsapp \d{2,}$", re.IGNORECASE)


class TemplateParamsError(ValueError):
    """The template cannot be sent with these values. The message is user-facing."""


class TemplateUnavailableError(TemplateParamsError):
    """The template list could not be read, so nothing can be checked right now."""


def sanitise_value(value: str | None) -> str:
    """One line, single spaces, trimmed (Meta rejects newlines, tabs, long gaps).

    Returns "" when nothing visible is left.
    """
    text = re.sub(r"\s+", " ", str(value or ""))
    text = "".join(c for c in text if unicodedata.category(c) != "Cc").strip()
    if all(unicodedata.category(c)[0] in "CZ" for c in text):
        return ""
    return text


def fetch_templates(fetch) -> list:
    """Call ``get_all_templates``; any failure reads as "no templates"."""
    try:
        return fetch() or []
    except Exception as e:
        logger.warning("Could not load templates", extra={"error": str(e)})
        return []


def _container_meta(template: dict) -> dict:
    raw = template.get("containerMeta")
    if not raw:
        return {}
    try:
        meta = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return {}
    return meta if isinstance(meta, dict) else {}


def template_variable_count(template: dict) -> int:
    """Distinct {{n}} in the template body. Raises if we cannot be sure."""
    meta = _container_meta(template)
    body = template.get("data") or meta.get("data")
    if not isinstance(body, str) or not body.strip():
        raise TemplateParamsError(
            "Could not read this template's text, so its variables cannot be checked."
        )
    outside_body = [str(meta.get("header") or "")] + [
        str(button.get("url") or "")
        for button in meta.get("buttons") or []
        if isinstance(button, dict)
    ]
    if any(_VARIABLE_RE.search(text) for text in outside_body):
        raise TemplateParamsError(
            "This template has variables in its header or button link, "
            "which broadcasts do not support."
        )
    names = set(_VARIABLE_RE.findall(body))
    if names != {str(n) for n in range(1, len(names) + 1)}:
        raise TemplateParamsError(
            "This template's variables are not numbered {{1}}, {{2}}, ... in order, "
            "which broadcasts do not support."
        )
    return len(names)


def _normalise_item(item, position: int):
    label = f"{{{{{position}}}}}"
    if isinstance(item, dict):
        token = str(item.get("token") or "").strip("{}")
        if token not in NAME_TOKENS:
            raise TemplateParamsError(f"Variable {label} has an unknown token.")
        return {
            "token": token,
            "fallback": sanitise_value(item.get("fallback")) or DEFAULT_FALLBACK,
        }
    if not isinstance(item, str):
        raise TemplateParamsError(f"Variable {label} must be text.")
    text = sanitise_value(item)
    if not text:
        raise TemplateParamsError(f"Variable {label} is empty.")
    whole = _WHOLE_TOKEN_RE.match(text)
    if whole:
        return _normalise_item({"token": whole.group(1)}, position)
    if _EMBEDDED_TOKEN_RE.search(text):
        raise TemplateParamsError(
            f"Variable {label}: a name token must be the whole value, "
            "not part of a longer text."
        )
    return text


def normalise_param_spec(raw) -> list:
    """Accepts a list or its JSON string; returns the stored form."""
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raise TemplateParamsError("template_params must be a JSON array.") from None
    if not isinstance(raw, list):
        raise TemplateParamsError("template_params must be a JSON array.")
    return [_normalise_item(item, i) for i, item in enumerate(raw, start=1)]


def check_template_params(templates: list, template_id: str, raw) -> tuple[dict, list]:
    """(template, spec) when the values fit the template exactly, else raise."""
    if not templates:
        raise TemplateUnavailableError(
            "Template list temporarily unavailable, so the template's variables "
            "could not be checked. Nothing was sent; try again shortly."
        )
    template = next((t for t in templates if t.get("id") == template_id), None)
    if template is None:
        raise TemplateParamsError(
            "Template not found, so its variables could not be checked."
        )
    spec = normalise_param_spec(raw)
    expected = template_variable_count(template)
    if len(spec) != expected:
        name = template.get("elementName") or template_id
        raise TemplateParamsError(
            f"Template '{name}' needs {expected} variable value(s) "
            f"but {len(spec)} were provided."
        )
    return template, spec


def _lead_name(phone: str) -> str:
    name = sanitise_value((find_lead_by_phone(phone) or {}).get("name"))
    if _AUTO_NAME_RE.match(name) or not any(c.isalpha() for c in name):
        return ""
    return name


def _first_name(name: str) -> str:
    for word in name.split():
        if any(c.isalpha() for c in word):
            word = word.rstrip(",;")
            return word[:1].upper() + word[1:]
    return ""


def resolve_params(spec: list, phone: str) -> list[str]:
    """The values for one recipient. Never contains an empty string."""
    name = None
    values = []
    for item in spec:
        if isinstance(item, str):
            values.append(item)
            continue
        if name is None:
            name = _lead_name(phone)
        value = _first_name(name) if item["token"] == "first_name" else name
        values.append(value or item["fallback"])
    return values


def fill_variables(text: str, values: list[str]) -> str:
    def fill(match: re.Match) -> str:
        key = match.group(1)
        if key.isdigit() and 0 < int(key) <= len(values):
            return values[int(key) - 1]
        return match.group(0)

    return _VARIABLE_RE.sub(fill, text)


def render_message(template: dict, values: list[str]) -> str:
    """The body as the recipient reads it, without Gupshup's button suffix."""
    body = _container_meta(template).get("data") or (
        template.get("data") or ""
    ).split("|")[0]
    return fill_variables(body.strip(), values)
