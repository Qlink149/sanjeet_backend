"""One-time backfill: schedule retries for existing retriable campaign failures.

Usage:
  python scripts/backfill_campaign_retries.py
  python scripts/backfill_campaign_retries.py --campaign-id <uuid>
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from qlink_chatbot.utils.campaign_retry import backfill_recipient_retries


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill campaign retry schedules")
    parser.add_argument("--campaign-id", help="Limit to one campaign_id")
    parser.add_argument(
        "--delay-hours",
        type=int,
        default=3,
        help="Hours from failed_at until retry (default 3)",
    )
    args = parser.parse_args()
    result = backfill_recipient_retries(
        args.campaign_id,
        delay_hours=args.delay_hours,
    )
    print(result)


if __name__ == "__main__":
    main()
