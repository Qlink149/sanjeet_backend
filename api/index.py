import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qlink_chatbot.main import app

__all__ = ["app"]
