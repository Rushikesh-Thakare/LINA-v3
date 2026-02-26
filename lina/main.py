"""
LINA v3 — Application Entry Point
Boots the PyQt5 app and launches the main window.
"""

import sys
import logging
from PyQt5.QtWidgets import QApplication
from lina.ui.main_window import MainWindow
from lina import __version__

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("lina.main")


def main() -> None:
    log.info("Starting LINA v%s", __version__)
    app = QApplication(sys.argv)
    app.setApplicationName("LINA")
    app.setApplicationVersion(__version__)

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
