"""Re-apply the pipeline rule after teaching it that sheet status "Done" means converted.

The master sheet's vocabulary ("Done", "3; Done", "Done; Invited & Attending")
is not in map_pipeline(), which fell through to its "nurture" default. With
confident_pipeline() now mapping it to "converted", this re-derives pipeline for
every lead that carries a status_raw.

An explicit signal still wins: "Done; Above Budget" stays not_now.

Writes an undo file recording every change, so any subset can be reverted with
--revert-from <file> [--only-from <pipeline>].

    python scripts/reclassify_done_as_converted.py --dry-run
    python scripts/reclassify_done_as_converted.py --apply --undo undo.json
    python scripts/reclassify_done_as_converted.py --revert-from undo.json --only-from discontinued
"""

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qlink_chatbot.database.collections import leads  # noqa: E402
from qlink_chatbot.database.master_import import confident_pipeline  # noqa: E402


def build_plan():
    plan = []
    cursor = leads.find(
        {"status_raw": {"$nin": [None, ""]}},
        {"lead_id": 1, "pipeline": 1, "status_raw": 1, "name": 1},
    )
    for doc in cursor:
        want = confident_pipeline(doc.get("status_raw") or "")
        if want and want != doc.get("pipeline"):
            plan.append(
                {
                    "lead_id": doc["lead_id"],
                    "name": doc.get("name"),
                    "from": doc.get("pipeline"),
                    "to": want,
                    "status_raw": doc.get("status_raw"),
                }
            )
    return plan


def summarise(plan):
    counts = collections.Counter((p["from"], p["to"]) for p in plan)
    for (a, b), n in counts.most_common():
        print(f"   {str(a):14} -> {str(b):14} {n}")
    print(f"   total: {len(plan)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", help="where to write the undo record when applying")
    ap.add_argument("--revert-from", help="undo file to revert from")
    ap.add_argument("--only-from", help="with --revert-from: revert only rows whose 'from' was this")
    args = ap.parse_args()

    if args.revert_from:
        rows = json.loads(Path(args.revert_from).read_text("utf-8"))
        if args.only_from:
            rows = [r for r in rows if r["from"] == args.only_from]
        print(f"reverting {len(rows)} lead(s)")
        for row in rows:
            leads.update_one({"lead_id": row["lead_id"]}, {"$set": {"pipeline": row["from"]}})
        print("done")
        return

    plan = build_plan()
    print("pipeline changes implied by the Done->converted rule:")
    summarise(plan)

    if not args.apply:
        print("\nDRY RUN — nothing written.")
        return

    if not args.undo:
        raise SystemExit("Refusing to apply without --undo <file>.")
    Path(args.undo).write_text(json.dumps(plan, indent=2, default=str), encoding="utf-8")
    print(f"\nundo record -> {args.undo}")

    for row in plan:
        leads.update_one({"lead_id": row["lead_id"]}, {"$set": {"pipeline": row["to"]}})
    print(f"applied: {len(plan)}")

    totals = collections.Counter(d.get("pipeline") for d in leads.find({}, {"pipeline": 1}))
    print("\npipeline totals now:")
    for k, v in sorted(totals.items(), key=lambda kv: -kv[1]):
        print(f"   {str(k):14} {v}")


if __name__ == "__main__":
    main()
