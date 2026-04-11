"""Photobooth application entry point."""

import sys
import logging

from PyQt6.QtWidgets import QApplication, QMessageBox

from src.config import settings
from src.camera import create_camera, MockCamera
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
    try:
        camera.open()
    except Exception as e:
        logger.error("Failed to open camera: %s", e)
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle("Camera Error")
        msg.setText(str(e))
        msg.setInformativeText("Falling back to mock camera mode.")
        msg.exec()
        camera = MockCamera()
        camera.open()

    window = AppWindow(camera)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
