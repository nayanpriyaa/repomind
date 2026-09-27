"""HTTP layer. Importing this package requires FastAPI and Pydantic."""

from __future__ import annotations

__all__ = ["create_app"]


def __getattr__(name: str):  # noqa: ANN202 - PEP 562 lazy re-export
    """Expose ``create_app`` without importing FastAPI at package import time."""
    if name == "create_app":
        from .main import create_app

        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
