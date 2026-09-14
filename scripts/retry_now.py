"""Set due retries to now and optionally run the retry cron locally."""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qlink_chatbot.database.collections import campaigns
from qlink_chatbot.utils.campaign_retry import run_due_campaign_retries

DEFAULT_CAMPAIGN_ID = "c15c9e75-9cf2-4011-a55e-a86f23a741cb"


def set_retry_now(campaign_id: str) -> int:
    now = datetime.now(timezone.utc)
    doc = campaigns.find_one({"campaign_id": campaign_id})
    if not doc:
        raise SystemExit(f"Campaign not found: {campaign_id}")

    updated = 0
    for i, rec in enumerate(doc.get("recipients") or []):
        if rec.get("status") not in ("failed", "undelivered"):
            continue
        if not rec.get("retry_at"):
            continue
        if (rec.get("retry_count") or 0) >= 1:
            continue
        campaigns.update_one(
            {"campaign_id": campaign_id},
            {
                "$set": {
                    f"recipients.{i}.retry_at": now,
                    f"recipients.{i}.retry_count": rec.get("retry_count") or 0,
                    f"recipients.{i}.retry_in_progress": False,
                }
            },
        )
        updated += 1
    return updated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign-id", default=DEFAULT_CAMPAIGN_ID)
    parser.add_argument(
        "--runs",
        type=int,
        default=3,
        help="How many cron batches to run locally (40 recipients each)",
    )
    args = parser.parse_args()

    due_now = set_retry_now(args.campaign_id)
    print({"retry_at_set_to_now": due_now})

    total_claimed = 0
    for run in range(1, args.runs + 1):
        summary = run_due_campaign_retries()
        print({"run": run, **summary})
        total_claimed += summary.get("claimed", 0)
        if summary.get("claimed", 0) == 0:
            break

    print({"total_claimed_this_session": total_claimed})


if __name__ == "__main__":
    main()
