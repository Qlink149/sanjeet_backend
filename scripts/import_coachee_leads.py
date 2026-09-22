"""Import coachee_leads.json into Mongo sanjeet.leads (one person per phone)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qlink_chatbot.database.collections import leads  # noqa: E402
from qlink_chatbot.database.leads import import_coachee_json  # noqa: E402

JSON_PATH = ROOT / "data" / "coachee_leads.json"


def main():
    if not JSON_PATH.exists():
        raise SystemExit(f"Missing {JSON_PATH}")

    replace = "--replace" in sys.argv
    if not replace:
        # Without --replace this calls insert_many() with no dedup against the
        # existing collection, which silently creates duplicate contacts. This
        # script is a one-shot bootstrap for an empty collection; for ongoing
        # imports use scripts/import_master_contacts.py, which merges.
        raise SystemExit(
            "This script only does a full replace of an empty collection. "
            "Running it without --replace would insert duplicates. "
            "To merge new contacts, use scripts/import_master_contacts.py."
        )
    if replace:
        # --replace wipes the whole leads collection, including quiz archetypes,
        # masterclass registrations and everything imported from the master sheet.
        existing = leads.count_documents({})
        print(f"--replace will DELETE all {existing} lead documents first.")
        print("This destroys quiz and masterclass state and cannot be undone.")
        if input(f"Type 'DELETE {existing}' to proceed: ").strip() != f"DELETE {existing}":
            raise SystemExit("Aborted — nothing was deleted.")

    payload = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    result = import_coachee_json(payload, replace=replace)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
