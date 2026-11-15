from starlette.responses import Response

from app.utils.config import settings

REFRESH_COOKIE = "refresh_token"
# Only the session routes ever see the cookie
REFRESH_COOKIE_PATH = "/api/v1/session"


def set_refresh_cookie(response: Response, raw: str) -> None:
    # No Domain attribute: the cookie stays host-only, so it never reaches a subdomain such as api.bckpack.ing
    response.set_cookie(
        REFRESH_COOKIE,
        raw,
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        path=REFRESH_COOKIE_PATH,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite="strict",
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite="strict",
    )
