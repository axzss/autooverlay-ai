"""Central logging configuration for AutoOverlay AI backend."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_DIR = Path(os.getenv("LOG_DIR") or "logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_PATH = LOG_DIR / "autooverlay.log"

_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def configure() -> None:
    """Install a root + app logger with rotating file output."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    fmt = logging.Formatter(_FORMAT)

    file_handler = RotatingFileHandler(
        LOG_PATH,
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)
    root.addHandler(console_handler)

    logging.getLogger("uvicorn.access").setLevel(logging.INFO)


def get_bot_logger() -> logging.Logger:
    return logging.getLogger("autooverlay.bot")
