import httpx
import structlog

from app.utils.config import settings

logger = structlog.get_logger()

RESEND_URL = "https://api.resend.com/emails"


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=10.0)


async def send_email(to: str, subject: str, text: str, html: str) -> None:
    """Send one email through Resend. Never raises: it runs as a background task, after the response.

    Bodies can hold single-use links, so they're logged only at DEBUG.
    """
    if settings.resend_api_key is None:
        logger.warning("email_not_configured", to=to, subject=subject)
        logger.debug("email_not_configured_body", to=to, text=text)
        return

    try:
        async with _client() as client:
            response = await client.post(
                RESEND_URL,
                headers={"Authorization": f"Bearer {settings.resend_api_key.get_secret_value()}"},
                json={
                    "from": settings.email_from,
                    "to": [to],
                    "subject": subject,
                    "text": text,
                    "html": html,
                },
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error("email_send_failed", status_code=exc.response.status_code)
    except httpx.HTTPError as exc:
        # The exception's message can include the request; log only its type
        logger.error("email_send_failed", error=type(exc).__name__)
    else:
        logger.info("email_sent", subject=subject)
