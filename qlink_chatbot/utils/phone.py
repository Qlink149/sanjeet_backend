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
    # 91 + stray trunk 0 + 10-digit mobile (e.g. 9109870777200), a common
    # data-entry error; it is the same person as 919870777200.
    if len(d) == 13 and d.startswith("910") and d[3] in "6789":
        return "91" + d[3:]
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


def phone_lookup_variants(phone: str | None) -> list[str]:
    """All stored forms worth matching (91-prefixed, 10-digit India, raw input)."""
    raw = str(phone or "").strip()
    stored = normalize_wa_phone(phone) or digits_only(phone) or raw
    variants = {stored, raw, digits_only(phone)}
    if stored.startswith("91") and len(stored) > 10:
        variants.add(stored[2:])
    if len(stored) == 10 and stored[0] in "6789":
        variants.add("91" + stored)
    return [v for v in variants if v]


_MULTI_NUMBER_SPLIT_RE = re.compile(r"[/,;|\n]+|\s+or\s+", re.IGNORECASE)


def split_phone_candidates(raw) -> list[str]:
    """A cell can hold several numbers ('98xxxxxx01 / 99xxxxxx02'). Split it."""
    text = str(raw or "").strip()
    if not text:
        return []
    return [part.strip() for part in _MULTI_NUMBER_SPLIT_RE.split(text) if part.strip()]


def is_valid_wa_phone(normalized: str | None) -> bool:
    """A normalized number we can plausibly send to (digits only, sane length)."""
    n = normalized or ""
    if not n.isdigit() or not 11 <= len(n) <= 15:
        return False
    if n.startswith("91"):
        return len(n) == 12 and n[2] in "6789"
    return True


def first_valid_phone(raw) -> str:
    """Best number in a cell: an India/UAE number first (what we can WhatsApp),
    else the first valid international one, else the first candidate."""
    candidates = [
        normalize_wa_phone(c) for c in (split_phone_candidates(raw) or [str(raw or "")])
    ]
    candidates = [n for n in candidates if n]
    for n in candidates:
        if classify_phone(n)[1]:
            return n
    for n in candidates:
        if is_valid_wa_phone(n):
            return n
    return candidates[0] if candidates else ""


def normalize_phone_list(phones: list | None) -> list[str]:
    """Normalize and de-duplicate. One number per input (the first valid one), so
    a person listed with two numbers is never messaged twice."""
    out: list[str] = []
    seen: set[str] = set()
    for phone in phones or []:
        n = first_valid_phone(phone) or str(phone or "").strip()
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def partition_phones(phones: list | None) -> tuple[list[str], list[str]]:
    """(valid, invalid): de-duplicated sendable numbers, and the unusable inputs."""
    valid = []
    invalid = []
    for n in normalize_phone_list(phones):
        (valid if is_valid_wa_phone(n) else invalid).append(n)
    return valid, invalid


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


def inbound_matches_masterclass_trigger(
    text: str | None,
    phrases: tuple[str, ...] | list[str],
) -> bool:
    """Quiz CTA phrases (substring) or exact Yes quick-reply (not 'yesterday')."""
    haystack = normalize_trigger_text(text)
    if not haystack:
        return False
    if haystack == "yes":
        return True
    return any(normalize_trigger_text(p) in haystack for p in phrases)
