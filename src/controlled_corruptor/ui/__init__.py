"""Optional PySide6 desktop UI. Import lazily via :func:`app.main`."""

from __future__ import annotations

__all__ = ["main"]


def main(argv=None):
    from .app import main as _main

    return _main(argv)
