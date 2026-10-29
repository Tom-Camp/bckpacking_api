import json
import logging
from collections.abc import Generator

import pytest
import structlog

from app.utils.logging import configure_logging

UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


@pytest.fixture(autouse=True)
def restore_logging() -> Generator[None]:
    """configure_logging mutates global logging state; put it back after each test."""
    root = logging.getLogger()
    saved_root = (root.handlers[:], root.level)
    saved = {
        name: (logging.getLogger(name).handlers[:], logging.getLogger(name).propagate)
        for name in UVICORN_LOGGERS
    }
    yield
    root.handlers, root.level = saved_root
    for name, (handlers, propagate) in saved.items():
        logging.getLogger(name).handlers = handlers
        logging.getLogger(name).propagate = propagate
    structlog.reset_defaults()


def test_uvicorn_loggers_go_through_root_handler(capsys: pytest.CaptureFixture[str]) -> None:
    # What uvicorn's LOGGING_CONFIG does before it imports the app
    for name in UVICORN_LOGGERS:
        logging.getLogger(name).handlers = [logging.StreamHandler()]
        logging.getLogger(name).propagate = False

    configure_logging(json_logs=True)
    logging.getLogger("uvicorn.error").info("Application startup complete.")

    for name in UVICORN_LOGGERS:
        assert logging.getLogger(name).handlers == []
        assert logging.getLogger(name).propagate is True
    line = json.loads(capsys.readouterr().out.strip())
    assert line["event"] == "Application startup complete."
    assert line["logger"] == "uvicorn.error"
