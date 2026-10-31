import logging
import sys
from typing import TextIO

import structlog


def configure_logging(
    log_level: str = "INFO", json_logs: bool = False, stream: TextIO | None = None
) -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    # Both structlog and stdlib records (uvicorn, alembic, ...) are rendered once, by the handler's formatter
    renderer: list[structlog.types.Processor]
    if json_logs:
        # JSONRenderer can't serialize exc_info, so render the traceback into an "exception" string first
        renderer = [structlog.processors.format_exc_info, structlog.processors.JSONRenderer()]
    else:
        renderer = [structlog.dev.ConsoleRenderer()]
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, *renderer],
    )

    handler = logging.StreamHandler(stream or sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(level)

    # uvicorn gives its loggers their own plain-text handlers; send them through the root handler instead.
    # A propagated record is checked only against its own logger's level, so uvicorn's --log-level (INFO by
    # default) would let INFO lines past a stricter LOG_LEVEL: give its loggers LOG_LEVEL too. This is per
    # logger rather than on the handler so a caller can still raise one logger (alembic, in migrations/env.py).
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
        logging.getLogger(name).setLevel(level)

    # Quiet noisy loggers, but never below LOG_LEVEL
    for name in ("uvicorn.access", "sqlalchemy.engine"):
        logging.getLogger(name).setLevel(max(level, logging.WARNING))

    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
