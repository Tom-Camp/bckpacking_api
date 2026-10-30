import io
import json
import logging
from collections.abc import Callable, Generator
from typing import Any

import httpx
import pytest
import structlog
from pydantic import SecretStr

from app.services import email as email_service
from app.utils.config import settings
from app.utils.logging import configure_logging

_LINK = "https://ui.example/reset-password#secret-token"


def _mock_client(monkeypatch: pytest.MonkeyPatch, handler: httpx.MockTransport) -> None:
    monkeypatch.setattr(email_service, "_client", lambda: httpx.AsyncClient(transport=handler))


async def _send() -> None:
    await email_service.send_email("hiker@example.com", "Reset", f"Open {_LINK}", f"<a href='{_LINK}'>x</a>")


@pytest.fixture
def configured_logs(monkeypatch: pytest.MonkeyPatch) -> Generator[Callable[[str], io.StringIO]]:
    """Configure logging as the app does, at a given LOG_LEVEL, into a buffer; restore it afterwards."""
    root = logging.getLogger()
    root_handlers, root_level = root.handlers[:], root.level
    structlog_config = structlog.get_config()

    def configure(level: str) -> io.StringIO:
        out = io.StringIO()
        configure_logging(log_level=level, json_logs=True, stream=out)
        # The module's logger caches the configuration it first saw; give it one that sees this one
        monkeypatch.setattr(email_service, "logger", structlog.get_logger())
        return out

    yield configure
    root.handlers = root_handlers
    root.setLevel(root_level)
    structlog.configure(**structlog_config)


def _lines(out: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in out.getvalue().splitlines()]


@pytest.mark.parametrize("level", ["INFO", "DEBUG"])
async def test_without_a_key_nothing_is_sent_and_the_link_is_logged_only_at_debug(
    monkeypatch: pytest.MonkeyPatch, configured_logs: Callable[[str], io.StringIO], level: str
) -> None:
    monkeypatch.setattr(settings, "resend_api_key", None)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200)

    _mock_client(monkeypatch, httpx.MockTransport(handler))
    out = configured_logs(level)

    await _send()

    assert requests == []
    lines = _lines(out)
    [warning] = [line for line in lines if line["event"] == "email_not_configured"]
    assert warning["level"] == "warning"
    assert warning["to"] == "hiker@example.com"
    with_link = [line for line in lines if "secret-token" in json.dumps(line)]
    if level == "DEBUG":
        assert [line["level"] for line in with_link] == ["debug"]
    else:
        assert with_link == []


async def test_with_a_key_posts_to_resend(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings, "resend_api_key", SecretStr("re_test_key"))
    monkeypatch.setattr(settings, "email_from", "bckpack.ing <no-reply@bckpack.ing>")
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"id": "abc"})

    _mock_client(monkeypatch, httpx.MockTransport(handler))

    with caplog.at_level(logging.DEBUG):
        await _send()

    [request] = requests
    assert request.method == "POST"
    assert str(request.url) == "https://api.resend.com/emails"
    assert request.headers["Authorization"] == "Bearer re_test_key"
    assert json.loads(request.content) == {
        "from": "bckpack.ing <no-reply@bckpack.ing>",
        "to": ["hiker@example.com"],
        "subject": "Reset",
        "text": f"Open {_LINK}",
        "html": f"<a href='{_LINK}'>x</a>",
    }
    for record in caplog.records:
        assert "re_test_key" not in record.getMessage()
        assert "secret-token" not in record.getMessage()


@pytest.mark.parametrize("status_code", [422, 500])
async def test_resend_error_is_logged_and_not_raised(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, status_code: int
) -> None:
    monkeypatch.setattr(settings, "resend_api_key", SecretStr("re_test_key"))
    _mock_client(monkeypatch, httpx.MockTransport(lambda r: httpx.Response(status_code)))

    await _send()

    [record] = [r for r in caplog.records if "email_send_failed" in r.getMessage()]
    assert record.levelno == logging.ERROR
    assert str(status_code) in record.getMessage()


async def test_network_error_is_logged_and_not_raised(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings, "resend_api_key", SecretStr("re_test_key"))

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    _mock_client(monkeypatch, httpx.MockTransport(handler))

    await _send()

    assert any("email_send_failed" in r.getMessage() for r in caplog.records)
