"""Desktop UI entry point.

PySide6 is an optional dependency. If it is not installed we print a friendly
hint instead of crashing, so a headless/CLI-only install still works.
"""

from __future__ import annotations

import sys
from typing import List, Optional


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    try:
        from PySide6.QtWidgets import QApplication
    except Exception:  # pragma: no cover - depends on environment
        print("The desktop UI needs PySide6. Install it with:\n"
              "    pip install 'controlled-corruptor[gui]'\n"
              "or:\n"
              "    pip install PySide6", file=sys.stderr)
        return 1

    from .main_window import MainWindow

    app = QApplication(argv)
    window = MainWindow()

    # Optional: open a file passed on the command line.
    file_args = [a for a in argv[1:] if not a.startswith("-")]
    if file_args:
        try:
            window.load_path(file_args[0])
        except Exception as exc:
            print(f"could not open {file_args[0]}: {exc}", file=sys.stderr)

    window.show()
    return app.exec()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
