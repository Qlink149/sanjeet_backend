"""WhatsApp phone normalization and masterclass inbound matching."""

from __future__ import annotations

import re
import unicodedata

_PUNCT_RE = re.compile(r"[^a-z0-9\s]+")
_SPACE_RE = re.compile(r"\s+")


def digits_only(raw: str | None) -> str:
    return re.sub(r"\D", "", raw or "")


def normalize_wa_phone(raw: str | None) -> str:
    """Digits-only E.164-ish (no plus). India → 91…, UAE → 9715…."""
    d = digits_only(raw)
    if not d:
        return ""
    if d.startswith("00"):
        d = d[2:]

    if len(d) == 12 and d.startswith("91") and d[2] in "6789":
        return d
    if len(d) == 10 and d[0] in "6789":
        return "91" + d
    if len(d) == 11 and d.startswith("0") and d[1] in "6789":
        return "91" + d[1:]

    if d.startswith("971"):
        rest = d[3:]
        if rest.startswith("0"):
            rest = rest[1:]
        if len(rest) == 9 and rest[0] == "5":
            return "971" + rest
        return d
    if len(d) == 10 and d.startswith("05"):
        return "971" + d[1:]
    if len(d) == 9 and d[0] == "5":
        return "971" + d

    return d


def classify_phone(raw: str | None) -> tuple[str, bool]:
    """Return (phone_class, whatsapp_ready) from the actual digits."""
    d = digits_only(raw)
    if not d:
        return "missing", False
    norm = normalize_wa_phone(raw)
    if len(norm) == 12 and norm.startswith("91") and norm[2] in "6789":
        return "india_91", True
    if len(norm) == 12 and norm.startswith("971") and norm[3] == "5":
        return "uae", True
    return "other_international", False


def _flatten_numbers(*parts) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()

    def add(value):
        if not value:
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                add(item)
            return
        text = str(value).strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)

    for part in parts:
        add(part)
    return out


def pick_sendable_phone(*parts) -> tuple[str, str, bool]:
    """First India/UAE number wins. Returns (stored, phone_class, ready)."""
    values = _flatten_numbers(*parts)
    for raw in values:
        cls, ready = classify_phone(raw)
        if ready:
            return normalize_wa_phone(raw), cls, True
    if values:
        raw = values[0]
        cls, ready = classify_phone(raw)
        return normalize_wa_phone(raw) or digits_only(raw), cls, False
    return "", "missing", False


def normalize_phone_list(phones: list | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for phone in phones or []:
        n = normalize_wa_phone(phone) or str(phone or "").strip()
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def normalize_trigger_text(text: str | None) -> str:
    if not text:
        return ""
    folded = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    lowered = folded.lower().replace("'", "").replace("'", "")
    cleaned = _PUNCT_RE.sub(" ", lowered)
    return _SPACE_RE.sub(" ", cleaned).strip()


def inbound_matches_phrases(text: str | None, phrases: tuple[str, ...] | list[str]) -> bool:
    haystack = normalize_trigger_text(text)
    if not haystack:
        return False
    return any(normalize_trigger_text(p) in haystack for p in phrases)
