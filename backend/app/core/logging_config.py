"""
Logging configuration — file + console output for development.

In dev (DEBUG=True): logs go to console AND backend/logs/netguru.log (if writable)
In production: console only (container orchestrators capture stdout).
"""
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.config import settings

# Log directory relative to backend/
LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_FILE = LOG_DIR / "netguru.log"
MAX_BYTES = 10 * 1024 * 1024  # 10 MB
BACKUP_COUNT = 3

CONSOLE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
FILE_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"


def setup_logging() -> None:
    """Configure root logger with console + optional file handler."""
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)

    # Avoid duplicate handlers on reload
    if root.handlers:
        return

    # Console handler (always)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(CONSOLE_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
    root.addHandler(console)

    # File handler (dev only)
    if settings.DEBUG:
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                LOG_FILE,
                maxBytes=MAX_BYTES,
                backupCount=BACKUP_COUNT,
                encoding="utf-8",
            )
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(
                logging.Formatter(FILE_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
            )
            root.addHandler(file_handler)
        except OSError as exc:
            # Keep app startup healthy in read-only/non-writable containers.
            root.warning(
                "File logging disabled: cannot write to %s (%s)",
                LOG_FILE,
                exc,
            )

    # Silence noisy third-party loggers
    for noisy in ("httpcore", "httpx", "hpack", "urllib3", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
