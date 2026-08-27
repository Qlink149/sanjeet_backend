"""Vercel FastAPI entrypoint — re-exports the existing app."""

from qlink_chatbot.main import app

__all__ = ["app"]
