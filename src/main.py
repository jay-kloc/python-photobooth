"""Photobooth application entry point."""

import sys
import logging

from PyQt6.QtWidgets import QApplication

from src.config import settings
from src.camera import create_camera
from src.ui import AppWindow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    logger.info("Starting photobooth (camera mode: %s)", settings.camera_mode)

    app = QApplication(sys.argv)
    app.setApplicationName("Photobooth")

    camera = create_camera(settings.camera_mode)
    camera.open()

    window = AppWindow(camera)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
