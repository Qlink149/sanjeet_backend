"""Clean audience filters built on top of the raw lead data.

Each lead stores ONE raw ``source`` string such as
"Coaching Payment & Client Database › All Leads; Facebook Ad; ..." and a free
``products`` list that also holds personal notes about the person. Shown as-is,
the dropdowns had 60+ near-duplicate sources and 200+ "products".

This module groups them for filtering only. The stored data is never rewritten:
a group is a dropdown label plus a pattern, so it is fully reversible, and code
that relies on an exact raw value (for example the quiz reminders) is unaffected.
A person can belong to several groups; the "already received" guard still stops
anyone getting the same template twice.
"""

from __future__ import annotations

import re

_START = r"(?:^|;\s*)"  # start of one ";"-separated token
_END = r"(?:\s*;|$)"  # end of one token


def _token(name: str) -> str:
    return _START + name + _END


# (dropdown label, pattern, regex options)
SOURCE_GROUPS: list[tuple[str, str, str]] = [
    ("Phone contacts", _START + "Phone contacts", ""),
    ("Coaching database & leads", _START + "(?:Coaching Payment & Client Database|Coachee Data)", ""),
    ("Paying clients", "› Payments" + _END, ""),
    ("Paid ads (Facebook / MIT)", _START + "(?:Facebook Ad|Aashna FB Leads|MIT |Whats App Broadcast Mit)", ""),
    ("Via", _token("Via"), ""),
    ("Calendly", _token("Calendly"), ""),
    ("Instagram", "insta", "i"),
    ("Direct", _token("Direct"), ""),
    ("Money Ceiling Quiz", _token("Money Ceiling Quiz"), ""),
    ("Via 5X Money", _token("Via 5X Money"), ""),
    ("Masterclass", "Masterclass", ""),
    ("Collated leads (PDF)", _START + "Collated Leads", ""),
    ("Other / old contacts", _START + "(?:Old relationship|Returning|Did Discovery Call)", ""),
]

# labels shown by earlier versions, still accepted
SOURCE_ALIASES = {"Coaching Payment & Client Database (all, merged)": "Coaching database & leads"}

# (dropdown label, pattern matching any ONE entry of the products list)
PRODUCT_GROUPS: list[tuple[str, str]] = [
    ("Free Masterclass", r"^Free Masterclass$"),
    ("1-1 Coaching", r"^1-1 Coaching$"),
    ("The Fulfilment Project", r"^The Fulfilment Project$"),
    ("Evolve", r"^Evolve$"),
    ("Evolve+", r"^Evolve\+$"),
    ("The Meaning Of Money Workshop", r"^The Meaning Of Money Workshop$"),
    ("Money Or Passion", r"^Money Or Passion$"),
    ("Begin Again", r"^Begin Again$"),
    ("Making Shifts Happen", r"^Making Shifts Happen$"),
    ("Project Change", r"^Project Change$"),
    ("Becoming You", r"^Becoming You$"),
    ("Get Unstuck", r"^Get Unstuck(?: - Bonus)?$"),
    ("Support Group (Old Coachee)", r"^Support Group \(Old Coachee\)$"),
    ("How To Heal From A Breakup", r"^How To Heal From A Breakup$"),
    ("Business Coaching", r"^Business Coaching$"),
    ("Business Manifestation", r"^(?:The )?Business Manifestation (?:Program|Project)$"),
    ("5X Money", r"^5X Money$"),
    ("Quiz", r"^Quiz$"),
    ("Masterclass list", r"^Masterclass list(?: \(.*\))?$"),
    ("Masterclass registrations", r"^(?:Registered$|MC · )"),
]

# not programmes: currency markers
HIDDEN_PRODUCTS = {"INR", "AED"}
# An ungrouped product is only offered once this many people have it, so a new real
# programme appears on its own while one-off notes about people stay hidden.
MIN_UNGROUPED_PRODUCT = 15


def _source_group(label: str):
    label = SOURCE_ALIASES.get(label, label)
    return next((g for g in SOURCE_GROUPS if g[0] == label), None)


def source_condition(source: str):
    """Value for ``query["source"]``: the group's pattern, else an exact match."""
    group = _source_group(source)
    if not group:
        return source
    _, pattern, options = group
    condition = {"$regex": pattern}
    if options:
        condition["$options"] = options
    return condition


def product_condition(product: str):
    """Value for ``query["products"]``: the group's pattern, else an exact match."""
    for label, pattern in PRODUCT_GROUPS:
        if label == product:
            return {"$regex": pattern}
    return product


def _matches(pattern: str, options: str, text: str) -> bool:
    return bool(re.search(pattern, text, re.IGNORECASE if "i" in options else 0))


def _biggest_first(counts: dict[str, int]) -> dict[str, int]:
    return dict(sorted(((k, v) for k, v in counts.items() if v), key=lambda kv: -kv[1]))


def group_source_counts(raw_counts: dict[str, int]) -> dict[str, int]:
    """{raw source string: leads} -> {group label: leads}.

    A source that fits no group keeps its own entry, so nothing disappears.
    """
    out: dict[str, int] = {}
    for raw, n in raw_counts.items():
        hits = [label for label, pattern, options in SOURCE_GROUPS if _matches(pattern, options, raw)]
        for label in hits or [raw]:
            out[label] = out.get(label, 0) + n
    return _biggest_first(out)


def group_product_counts(rows: list[tuple[list[str], int]]) -> dict[str, int]:
    """[(a lead's products list, number of such leads)] -> {label: leads}.

    A lead holding two variants of one programme is counted once.
    """
    grouped: dict[str, int] = {}
    ungrouped: dict[str, int] = {}
    for products, n in rows:
        labels: set[str] = set()
        others: set[str] = set()
        for value in products or []:
            if not value or value in HIDDEN_PRODUCTS:
                continue
            hit = next((label for label, p in PRODUCT_GROUPS if re.search(p, value)), None)
            if hit:
                labels.add(hit)
            else:
                others.add(value)
        for label in labels:
            grouped[label] = grouped.get(label, 0) + n
        for value in others:
            ungrouped[value] = ungrouped.get(value, 0) + n
    grouped.update({k: v for k, v in ungrouped.items() if v >= MIN_UNGROUPED_PRODUCT})
    return _biggest_first(grouped)
