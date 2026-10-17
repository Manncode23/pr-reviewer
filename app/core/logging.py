"""Logging setup shared by the whole application."""

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Configure root logging once, at application startup."""
    root = logging.getLogger()
    if root.handlers:
        root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )
    root.addHandler(handler)
    root.setLevel(level.upper())

    # Keep noisy third-party loggers quiet
    for noisy in ("httpx", "httpcore", "urllib3", "google_genai", "google_genai.models"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Use as: logger = get_logger(__name__)"""
    return logging.getLogger(name)