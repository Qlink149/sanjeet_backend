"""FastAPI dependency enforcing the dashboard login token (see auth_token.py)."""

from fastapi.responses import JSONResponse
from starlette.requests import Request

from qlink_chatbot.utils.auth_token import TokenError, verify_token


class Unauthorized(Exception):
    pass


def register_auth_handler(app) -> None:
    """Render Unauthorized as the dashboard's {success, message} 401 JSON."""

    @app.exception_handler(Unauthorized)
    async def _handle(_request, _exc):
        return JSONResponse(
            {"success": False, "message": "Unauthorized"}, status_code=401
        )


async def require_dashboard_token(request: Request) -> dict:
    header = request.headers.get("authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer":
        raise Unauthorized()
    try:
        return verify_token(token.strip())
    except TokenError:
        raise Unauthorized()
