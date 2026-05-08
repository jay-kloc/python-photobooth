"""Full-screen photo slideshow — intended for a second display."""

import sys
import logging
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QFileSystemWatcher
from PyQt6.QtGui import QPixmap, QFont
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

PHOTOS_DIR = Path(__file__).resolve().parent / "photos"
SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".bmp"}
SLIDE_INTERVAL_MS = 5_000

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("slideshow")


def _sorted_photos() -> list[Path]:
    if not PHOTOS_DIR.exists():
        return []
    files = [p for p in PHOTOS_DIR.iterdir()
             if p.is_file() and p.suffix.lower() in SUPPORTED_EXT]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


class SlideshowWindow(QWidget):
    def __init__(self):
        super().__init__()
        self._photos: list[Path] = []
        self._index = 0
        self._setup_ui()
        self._setup_watcher()
        self._reload()

        self._slide_timer = QTimer(self)
        self._slide_timer.timeout.connect(self._advance)
        self._slide_timer.start(SLIDE_INTERVAL_MS)

    def _setup_ui(self):
        self.setWindowTitle("Slideshow")
        self.setStyleSheet("background-color: #000;")

        self._photo_label = QLabel(self)
        self._photo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._photo_label.setStyleSheet("background-color: #000;")

        self._empty_label = QLabel("Waiting for photos…", self)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setFont(QFont("Arial", 36))
        self._empty_label.setStyleSheet("color: #444; background-color: #000;")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        self._photo_label.setGeometry(0, 0, w, h)
        self._empty_label.setGeometry(0, 0, w, h)
        QTimer.singleShot(0, self._render)

    def _setup_watcher(self):
        PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        self._watcher = QFileSystemWatcher([str(PHOTOS_DIR)], self)
        self._watcher.directoryChanged.connect(self._on_dir_changed)

    def _on_dir_changed(self):
        prev_count = len(self._photos)
        self._photos = _sorted_photos()
        if len(self._photos) > prev_count:
            # New photo — show it immediately and reset the interval
            self._index = 0
            self._slide_timer.start(SLIDE_INTERVAL_MS)
            self._render()
        elif not self._photos:
            self._render()

    def _reload(self):
        self._photos = _sorted_photos()
        self._index = 0
        self._render()

    def _advance(self):
        if not self._photos:
            return
        self._index = (self._index + 1) % len(self._photos)
        self._render()

    def _render(self):
        if not self._photos:
            self._photo_label.hide()
            self._empty_label.show()
            return

        self._empty_label.hide()
        self._photo_label.show()

        path = self._photos[self._index % len(self._photos)]
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            self._advance()
            return
        self._photo_label.setPixmap(
            pixmap.scaled(
                self._photo_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.close()
        elif key == Qt.Key.Key_Right:
            self._slide_timer.start(SLIDE_INTERVAL_MS)
            self._advance()
        elif key == Qt.Key.Key_Left:
            if self._photos:
                self._slide_timer.start(SLIDE_INTERVAL_MS)
                self._index = (self._index - 1) % len(self._photos)
                self._render()


def main():
    app = QApplication(sys.argv)

    window = SlideshowWindow()

    screens = app.screens()
    if len(screens) > 1:
        target = screens[1]
        logger.info("Opening on screen 1: %s", target.name())
    else:
        target = screens[0]
        logger.info("Only one screen found, opening on screen 0")

    window.move(target.geometry().topLeft())
    window.showFullScreen()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
