"""Import coachee_leads.json into Mongo sanjeet.leads (one person per phone)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qlink_chatbot.database.leads import import_coachee_json  # noqa: E402

JSON_PATH = ROOT / "data" / "coachee_leads.json"


def main():
    if not JSON_PATH.exists():
        raise SystemExit(f"Missing {JSON_PATH}")
    payload = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    result = import_coachee_json(payload, replace=True)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
