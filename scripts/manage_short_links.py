"""Add / change / list the /go/<slug> redirect links.

    python scripts/manage_short_links.py seed
    python scripts/manage_short_links.py list
    python scripts/manage_short_links.py set coterie https://chat.whatsapp.com/XXXX "Coterie group"
    python scripts/manage_short_links.py set masterclass @masterclass
    python scripts/manage_short_links.py delete coterie

Template buttons use https://sanjeet.ray.claraai.tech/go/<slug>.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from qlink_chatbot.database.short_links import (  # noqa: E402
    MASTERCLASS_TARGET,
    delete_short_link,
    list_short_links,
    upsert_short_link,
)

SEED = [
    (
        "coterie",
        "https://chat.whatsapp.com/LsQjGBZ74fP2tDB1TWmQ5V",
        "The Coterie WhatsApp group",
    ),
    ("masterclass", MASTERCLASS_TARGET, "Joining link of the Active masterclass"),
]


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "list"
    if cmd == "seed":
        for slug, target, note in SEED:
            print("set", upsert_short_link(slug, target, note))
    elif cmd == "set" and len(argv) >= 4:
        print("set", upsert_short_link(argv[2], argv[3], argv[4] if len(argv) > 4 else ""))
    elif cmd == "delete" and len(argv) >= 3:
        print("deleted" if delete_short_link(argv[2]) else "not found")
    elif cmd == "list":
        for row in list_short_links():
            print(f"{row['slug']:20} {row['target']}  clicks={row.get('clicks', 0)}")
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
