"""Gallery panel — thumbnail grid of captured photos with full-screen viewer."""

import logging
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QFont, QPixmap, QKeyEvent
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QGridLayout, QSizePolicy, QStackedWidget,
)

from src.config import PHOTOS_DIR

logger = logging.getLogger(__name__)

THUMBNAIL_W = 260
THUMBNAIL_H = 190
GRID_COLS = 4
SUPPORTED_EXT = {".jpg", ".jpeg", ".png", ".bmp"}

_STYLE = """
QWidget { background-color: #1a1a1a; color: #eee; }
QPushButton {
    font-size: 18px; padding: 12px 24px; border: none;
    border-radius: 10px; color: white;
}
QLabel { color: #eee; }
QScrollBar:vertical {
    width: 18px; background: #2a2a2a; border-radius: 9px;
}
QScrollBar::handle:vertical {
    background: #666; border-radius: 9px; min-height: 50px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


def _sorted_photos() -> list[Path]:
    """Return photo files sorted newest-first."""
    files = [
        p for p in PHOTOS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXT
    ]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files


# ---------------------------------------------------------------------------
# Thumbnail widget
# ---------------------------------------------------------------------------

class _Thumbnail(QLabel):
    clicked = pyqtSignal(int)  # index in the photos list

    def __init__(self, index: int, path: Path, parent=None):
        super().__init__(parent)
        self._index = index
        self.setFixedSize(THUMBNAIL_W, THUMBNAIL_H)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("""
            QLabel {
                background-color: #111;
                border: 2px solid #333;
                border-radius: 8px;
            }
            QLabel:hover { border-color: #e74c3c; }
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            self.setPixmap(
                pixmap.scaled(
                    THUMBNAIL_W - 8, THUMBNAIL_H - 8,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self.setText("?")

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._index)


# ---------------------------------------------------------------------------
# Full-screen viewer
# ---------------------------------------------------------------------------

class _PhotoViewer(QWidget):
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._photos: list[Path] = []
        self._index = 0
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("background-color: #000;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Top bar
        bar = QWidget()
        bar.setFixedHeight(64)
        bar.setStyleSheet("background-color: #111;")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(16, 0, 16, 0)

        close_btn = QPushButton("✕  Close")
        close_btn.setMinimumSize(130, 50)
        close_btn.setStyleSheet("""
            QPushButton { background-color: #555; font-size: 20px; }
            QPushButton:hover { background-color: #666; }
            QPushButton:pressed { background-color: #444; }
        """)
        close_btn.clicked.connect(self.closed.emit)
        bar_layout.addWidget(close_btn)

        self._name_label = QLabel()
        self._name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._name_label.setStyleSheet("color: #aaa; font-size: 15px; background: transparent;")
        bar_layout.addWidget(self._name_label, stretch=1)

        self._counter_label = QLabel()
        self._counter_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._counter_label.setStyleSheet("color: #888; font-size: 15px; background: transparent; min-width: 80px;")
        bar_layout.addWidget(self._counter_label)

        layout.addWidget(bar)

        # Photo + nav arrows
        mid = QHBoxLayout()
        mid.setContentsMargins(0, 0, 0, 0)
        mid.setSpacing(0)

        self._prev_btn = QPushButton("❮")
        self._prev_btn.setFixedWidth(70)
        self._prev_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._prev_btn.setStyleSheet("""
            QPushButton { background-color: #1a1a1a; color: #aaa; font-size: 32px; border: none; border-radius: 0; }
            QPushButton:hover { background-color: #2a2a2a; color: #fff; }
            QPushButton:disabled { color: #333; }
        """)
        self._prev_btn.clicked.connect(self._go_prev)
        mid.addWidget(self._prev_btn)

        self._photo_label = QLabel()
        self._photo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._photo_label.setStyleSheet("background-color: #000;")
        self._photo_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        mid.addWidget(self._photo_label, stretch=1)

        self._next_btn = QPushButton("❯")
        self._next_btn.setFixedWidth(70)
        self._next_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self._next_btn.setStyleSheet("""
            QPushButton { background-color: #1a1a1a; color: #aaa; font-size: 32px; border: none; border-radius: 0; }
            QPushButton:hover { background-color: #2a2a2a; color: #fff; }
            QPushButton:disabled { color: #333; }
        """)
        self._next_btn.clicked.connect(self._go_next)
        mid.addWidget(self._next_btn)

        layout.addLayout(mid, stretch=1)

    def show_photo(self, photos: list[Path], index: int):
        self._photos = photos
        self._index = index
        self._update()

    def _update(self):
        if not self._photos:
            return
        path = self._photos[self._index]
        pixmap = QPixmap(str(path))
        if not pixmap.isNull():
            available = self._photo_label.size()
            if available.width() > 10 and available.height() > 10:
                pixmap = pixmap.scaled(
                    available,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            self._photo_label.setPixmap(pixmap)
        else:
            self._photo_label.setText("Could not load image")

        self._name_label.setText(path.name)
        self._counter_label.setText(f"{self._index + 1} / {len(self._photos)}")
        self._prev_btn.setEnabled(self._index > 0)
        self._next_btn.setEnabled(self._index < len(self._photos) - 1)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Re-scale the current photo to new size
        QTimer.singleShot(0, self._update)

    def _go_prev(self):
        if self._index > 0:
            self._index -= 1
            self._update()

    def _go_next(self):
        if self._index < len(self._photos) - 1:
            self._index += 1
            self._update()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Left:
            self._go_prev()
        elif event.key() == Qt.Key.Key_Right:
            self._go_next()
        elif event.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Return):
            self.closed.emit()


# ---------------------------------------------------------------------------
# Main gallery panel
# ---------------------------------------------------------------------------

class GalleryPanel(QWidget):
    """Full gallery with thumbnail grid and inline photo viewer."""

    back_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._photos: list[Path] = []
        self._setup_ui()

    def refresh(self):
        """Reload photos from disk and rebuild the grid."""
        self._photos = _sorted_photos()
        self._rebuild_grid()
        self._stack.setCurrentIndex(0)  # always open on grid view

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        self.setStyleSheet(_STYLE)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(72)
        header.setStyleSheet("background-color: #2a2a2a;")
        hdr = QHBoxLayout(header)
        hdr.setContentsMargins(16, 0, 16, 0)

        back_btn = QPushButton("< Back")
        back_btn.setMinimumSize(130, 54)
        back_btn.setStyleSheet("""
            QPushButton { background-color: #555; font-size: 22px; }
            QPushButton:hover { background-color: #666; }
            QPushButton:pressed { background-color: #444; }
        """)
        back_btn.clicked.connect(self.back_requested.emit)
        hdr.addWidget(back_btn)

        self._title_label = QLabel("Gallery")
        self._title_label.setFont(QFont("Arial", 26, QFont.Weight.Bold))
        self._title_label.setStyleSheet("color: white; background: transparent;")
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr.addWidget(self._title_label, stretch=1)

        # Spacer to balance the back button
        hdr.addSpacing(130)

        outer.addWidget(header)

        # Stack: index 0 = grid, index 1 = viewer
        self._stack = QStackedWidget()

        # -- Grid view --
        grid_container = QWidget()
        grid_outer = QVBoxLayout(grid_container)
        grid_outer.setContentsMargins(0, 0, 0, 0)
        grid_outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        self._grid_widget = QWidget()
        self._grid_layout = QGridLayout(self._grid_widget)
        self._grid_layout.setSpacing(12)
        self._grid_layout.setContentsMargins(24, 24, 24, 24)
        self._grid_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        scroll.setWidget(self._grid_widget)

        self._empty_label = QLabel("No photos yet.\nTake some photos first!")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet("color: #555; font-size: 24px;")
        self._empty_label.hide()

        grid_outer.addWidget(scroll, stretch=1)
        grid_outer.addWidget(self._empty_label)

        self._stack.addWidget(grid_container)

        # -- Viewer --
        self._viewer = _PhotoViewer()
        self._viewer.closed.connect(lambda: self._stack.setCurrentIndex(0))
        self._stack.addWidget(self._viewer)

        outer.addWidget(self._stack, stretch=1)

    def _rebuild_grid(self):
        # Clear old thumbnails
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not self._photos:
            self._empty_label.show()
            self._title_label.setText("Gallery")
            return

        self._empty_label.hide()
        count = len(self._photos)
        self._title_label.setText(f"Gallery  ({count} photo{'s' if count != 1 else ''})")

        for i, path in enumerate(self._photos):
            thumb = _Thumbnail(i, path)
            thumb.clicked.connect(self._open_viewer)
            row, col = divmod(i, GRID_COLS)
            self._grid_layout.addWidget(thumb, row, col)

    def _open_viewer(self, index: int):
        self._viewer.show_photo(self._photos, index)
        self._stack.setCurrentIndex(1)

    def keyPressEvent(self, event: QKeyEvent):
        if self._stack.currentIndex() == 1:
            self._viewer.keyPressEvent(event)
        elif event.key() == Qt.Key.Key_Escape:
            self.back_requested.emit()
