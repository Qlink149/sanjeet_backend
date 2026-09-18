"""List campaigns created in the last N hours."""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
env_path = ROOT / ".env"
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val

sys.path.insert(0, str(ROOT))

from qlink_chatbot.database.collections import campaigns  # noqa: E402

HOURS = int(sys.argv[1]) if len(sys.argv) > 1 else 2
cutoff = datetime.now(timezone.utc) - timedelta(hours=HOURS)
docs = list(campaigns.find({"created_at": {"$gte": cutoff}}).sort("created_at", -1))
print(f"Campaigns in last {HOURS} hour(s): {len(docs)}")
for doc in docs:
    recs = doc.get("recipients") or []
    st = Counter(r.get("status") or "unknown" for r in recs)
    created = doc.get("created_at")
    print(
        json.dumps(
            {
                "campaign_id": doc.get("campaign_id"),
                "template_name": doc.get("template_name"),
                "created_at": created.isoformat()
                if hasattr(created, "isoformat")
                else str(created),
                "total": len(recs),
                "status_breakdown": dict(st),
            },
            indent=2,
        )
    )
