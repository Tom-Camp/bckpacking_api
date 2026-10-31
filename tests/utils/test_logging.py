import io
import json
import logging
from collections.abc import Generator
from typing import Any

import pytest
import structlog

from app.utils.logging import configure_logging

UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")
# Every logger configure_logging changes, besides the root
TOUCHED_LOGGERS = (*UVICORN_LOGGERS, "sqlalchemy.engine")


def _is_pytest_handler(handler: logging.Handler) -> bool:
    # pytest swaps its capture handlers on the root for each test phase; leave those to pytest
    return type(handler).__module__.startswith("_pytest")


@pytest.fixture(autouse=True)
def restore_logging() -> Generator[None]:
    """configure_logging mutates global logging state; put back exactly what was there before."""
    root = logging.getLogger()
    root_handlers = [h for h in root.handlers if not _is_pytest_handler(h)]
    root_level = root.level
    loggers = {
        name: (logger.handlers[:], logger.propagate, logger.level)
        for name in TOUCHED_LOGGERS
        for logger in [logging.getLogger(name)]
    }
    structlog_config = structlog.get_config()
    yield
    root.handlers = root_handlers + [h for h in root.handlers if _is_pytest_handler(h)]
    root.setLevel(root_level)
    for name, (handlers, propagate, level) in loggers.items():
        logger = logging.getLogger(name)
        logger.handlers, logger.propagate = handlers, propagate
        logger.setLevel(level)
    structlog.configure(**structlog_config)


def _json_lines(stream: io.StringIO) -> list[dict[str, Any]]:
    return [json.loads(line) for line in stream.getvalue().splitlines()]


def test_uvicorn_loggers_go_through_root_handler() -> None:
    # What uvicorn's LOGGING_CONFIG does before it imports the app
    for name in UVICORN_LOGGERS:
        logging.getLogger(name).handlers = [logging.StreamHandler(io.StringIO())]
        logging.getLogger(name).propagate = False
    out = io.StringIO()

    configure_logging(json_logs=True, stream=out)
    logging.getLogger("uvicorn.error").info("Application startup complete.")

    for name in UVICORN_LOGGERS:
        assert logging.getLogger(name).handlers == []
        assert logging.getLogger(name).propagate is True
    [line] = _json_lines(out)
    assert line["event"] == "Application startup complete."
    assert line["logger"] == "uvicorn.error"


def test_structlog_events_are_rendered_once() -> None:
    out = io.StringIO()

    configure_logging(json_logs=True, stream=out)
    structlog.get_logger("app.test").info("request", status=200)

    [line] = _json_lines(out)
    assert line["event"] == "request"
    assert line["status"] == 200
    assert line["logger"] == "app.test"


def test_exceptions_include_the_traceback() -> None:
    out = io.StringIO()

    configure_logging(json_logs=True, stream=out)
    try:
        1 / 0  # noqa: B018
    except ZeroDivisionError:
        logging.getLogger("uvicorn.error").exception("Exception in ASGI application")
        structlog.get_logger("app.test").exception("unhandled")

    lines = _json_lines(out)
    assert [line["event"] for line in lines] == ["Exception in ASGI application", "unhandled"]
    for line in lines:
        assert "exc_info" not in line
        assert line["exception"].startswith("Traceback (most recent call last):")
        assert "ZeroDivisionError: division by zero" in line["exception"]


@pytest.mark.parametrize(
    ("log_level", "expected"), [("WARNING", ["shutting down"]), ("INFO", ["started", "shutting down"])]
)
def test_log_level_filters_uvicorn_records(log_level: str, expected: list[str]) -> None:
    # uvicorn sets its loggers to its own --log-level, INFO by default, before it imports the app
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    out = io.StringIO()

    configure_logging(log_level=log_level, json_logs=True, stream=out)
    logging.getLogger("uvicorn.error").info("started")
    logging.getLogger("uvicorn.error").warning("shutting down")

    assert [line["event"] for line in _json_lines(out)] == expected


def test_quiet_loggers_respect_a_stricter_log_level() -> None:
    configure_logging(log_level="ERROR")

    assert logging.getLogger("uvicorn.access").level == logging.ERROR
    assert logging.getLogger("sqlalchemy.engine").level == logging.ERROR


def test_a_logger_raised_after_configure_still_logs() -> None:
    # migrations/env.py keeps alembic at INFO whatever LOG_LEVEL is, so startup logs show which migrations ran
    alembic = logging.getLogger("alembic")
    alembic_level = alembic.level
    out = io.StringIO()

    configure_logging(log_level="WARNING", json_logs=True, stream=out)
    alembic.setLevel(logging.INFO)
    try:
        logging.getLogger("alembic.runtime.migration").info("Running upgrade")
    finally:
        alembic.setLevel(alembic_level)

    [line] = _json_lines(out)
    assert line["event"] == "Running upgrade"
