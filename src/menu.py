"""Main menu screen — entry point with Photobooth and Settings buttons."""

import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout,
)

logger = logging.getLogger(__name__)


class MainMenu(QWidget):
    """Main menu with two buttons: Photobooth and Settings."""

    start_photobooth = pyqtSignal()
    open_gallery = pyqtSignal()
    open_settings = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("background-color: #1a1a1a;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 40, 40, 40)

        layout.addStretch(2)

        # Title
        title = QLabel("Photobooth")
        title.setFont(QFont("Arial", 64, QFont.Weight.Bold))
        title.setStyleSheet("color: white;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # Subtitle
        subtitle = QLabel("Capture the moment")
        subtitle.setFont(QFont("Arial", 24))
        subtitle.setStyleSheet("color: #888;")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(subtitle)

        layout.addStretch(1)

        # Buttons — stacked vertically for easy touch
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(30)
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._photobooth_btn = QPushButton("  Start Photobooth  ")
        self._photobooth_btn.setMinimumSize(400, 100)
        self._photobooth_btn.setFont(QFont("Arial", 28, QFont.Weight.Bold))
        self._photobooth_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._photobooth_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                border: none;
                border-radius: 16px;
            }
            QPushButton:hover { background-color: #c0392b; }
            QPushButton:pressed { background-color: #a93226; }
        """)
        self._photobooth_btn.clicked.connect(self.start_photobooth.emit)
        btn_layout.addWidget(self._photobooth_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self._gallery_btn = QPushButton("  Gallery  ")
        self._gallery_btn.setMinimumSize(400, 100)
        self._gallery_btn.setFont(QFont("Arial", 28, QFont.Weight.Bold))
        self._gallery_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._gallery_btn.setStyleSheet("""
            QPushButton {
                background-color: #8e44ad;
                color: white;
                border: none;
                border-radius: 16px;
            }
            QPushButton:hover { background-color: #7d3c98; }
            QPushButton:pressed { background-color: #6c3483; }
        """)
        self._gallery_btn.clicked.connect(self.open_gallery.emit)
        btn_layout.addWidget(self._gallery_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        self._settings_btn = QPushButton("  Settings  ")
        self._settings_btn.setMinimumSize(400, 100)
        self._settings_btn.setFont(QFont("Arial", 28, QFont.Weight.Bold))
        self._settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #34495e;
                color: white;
                border: none;
                border-radius: 16px;
            }
            QPushButton:hover { background-color: #2c3e50; }
            QPushButton:pressed { background-color: #1a252f; }
        """)
        self._settings_btn.clicked.connect(self.open_settings.emit)
        btn_layout.addWidget(self._settings_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addLayout(btn_layout)

        layout.addStretch(2)
