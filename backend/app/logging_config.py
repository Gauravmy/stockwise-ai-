"""Logging setup. Logs request metadata and summary counts only — never dataset contents."""

import logging
import sys


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if any(getattr(h, "_stockwise", False) for h in root.handlers):
        root.setLevel(level.upper())
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    handler._stockwise = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level.upper())
