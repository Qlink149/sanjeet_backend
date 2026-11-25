"""Merged audience lists built from the raw ``source`` strings.

Each lead stores ONE raw source string such as
"Coaching Payment & Client Database › All Leads; Facebook Ad; ...", so the same
real-world list shows up as many separate dropdown entries. A merged list picks
everyone whose source mentions the list, once, so it can be broadcast in a single
send. Combined with the "already received" guard, nobody is messaged twice even if
they also appear in another list.
"""

import re

COACHING_PAYMENT_LABEL = "Coaching Payment & Client Database (all, merged)"
_COACHING_PAYMENT_TOKEN = "Coaching Payment & Client Database"

# dropdown label -> Mongo condition on the lead's ``source`` field
MERGED_SOURCE_LISTS = {
    COACHING_PAYMENT_LABEL: {"$regex": re.escape(_COACHING_PAYMENT_TOKEN)},
}


def source_condition(source: str):
    """Value for ``query["source"]``: a merged-list condition, else exact match."""
    return MERGED_SOURCE_LISTS.get(source, source)


def add_merged_source_counts(sources: dict[str, int], leads_collection) -> dict[str, int]:
    """Add the merged lists to the dropdown counts, biggest first."""
    out = dict(sources)
    for label, condition in MERGED_SOURCE_LISTS.items():
        out[label] = leads_collection.count_documents({"source": condition})
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))
