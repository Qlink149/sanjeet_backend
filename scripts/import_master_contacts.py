"""Merge Final_Master_Contact_Database_Updated.xlsx into Mongo sanjeet.leads.

Non-destructive: existing contacts keep their lead_id, quiz archetype,
masterclass registrations and engagement log.

    python scripts/import_master_contacts.py <path.xlsx> --dry-run
    python scripts/import_master_contacts.py <path.xlsx> --backup leads_backup.json
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qlink_chatbot.database.collections import leads  # noqa: E402
from qlink_chatbot.database.master_import import (  # noqa: E402
    merge_master_contacts,
    parse_master_sheet,
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx", help="path to the master contact spreadsheet")
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    ap.add_argument("--backup", help="write a JSON dump of leads before committing")
    args = ap.parse_args()

    path = Path(args.xlsx)
    if not path.exists():
        raise SystemExit(f"Missing {path}")

    if not args.dry_run and not args.backup:
        raise SystemExit(
            "Refusing to write without --backup <file>. "
            "Use --dry-run to preview instead."
        )

    rows = parse_master_sheet(str(path))
    print(f"Parsed {len(rows)} rows from {path.name}")

    if args.backup:
        dump = list(leads.find({}))
        Path(args.backup).write_text(
            json.dumps(dump, indent=2, default=str), encoding="utf-8"
        )
        print(f"Backed up {len(dump)} lead documents -> {args.backup}")

    result = merge_master_contacts(rows, dry_run=args.dry_run)
    print(json.dumps(result, indent=2, default=str))
    if args.dry_run:
        print("\nDRY RUN — nothing was written.")


if __name__ == "__main__":
    main()
