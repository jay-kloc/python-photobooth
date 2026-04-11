"""Live camera settings panel — ISO, shutter speed, aperture, and more."""

import logging

from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QDoubleSpinBox, QScrollArea, QGroupBox, QGridLayout,
    QSizePolicy,
)

from src.camera import Camera

logger = logging.getLogger(__name__)

_STYLE = """
QWidget { background-color: #1a1a1a; color: #eee; }
QGroupBox {
    font-size: 18px; font-weight: bold; color: #fff;
    border: 2px solid #444; border-radius: 10px;
    margin-top: 18px; padding-top: 22px;
}
QGroupBox::title { subcontrol-origin: margin; left: 16px; padding: 0 8px; }
QLabel { font-size: 17px; color: #ccc; }
QComboBox {
    font-size: 17px; padding: 10px 14px; min-height: 28px;
    border: 2px solid #555; border-radius: 8px;
    background: #2a2a2a; color: #fff;
}
QComboBox::drop-down { width: 36px; }
QComboBox QAbstractItemView { font-size: 17px; background: #2a2a2a; color: #fff; min-height: 36px; }
QComboBox:disabled { background: #222; color: #666; border-color: #333; }
QDoubleSpinBox {
    font-size: 17px; padding: 10px; min-height: 28px;
    border: 2px solid #555; border-radius: 8px;
    background: #2a2a2a; color: #fff;
}
QPushButton {
    font-size: 18px; padding: 12px 24px; border: none;
    border-radius: 10px; color: white;
}
QScrollBar:vertical {
    width: 18px; background: #2a2a2a; border-radius: 9px;
}
QScrollBar::handle:vertical {
    background: #666; border-radius: 9px; min-height: 50px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


class CameraPanel(QWidget):
    """Panel for adjusting camera settings (ISO, shutter, aperture, etc.)."""

    back_requested = pyqtSignal()

    def __init__(self, camera: Camera, parent=None):
        super().__init__(parent)
        self._camera = camera
        self._widgets: dict[str, QComboBox | QDoubleSpinBox] = {}
        self._pending: dict[str, str] = {}  # name → new value
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_camera(self, camera: Camera):
        self._camera = camera

    def refresh(self):
        """Reload settings from the camera (called when panel becomes visible)."""
        self._pending.clear()
        self._status_label.setText("Loading…")
        # Defer so the panel has time to render first
        QTimer.singleShot(50, self._load_settings)

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        self.setStyleSheet(_STYLE)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header
        header = QWidget()
        header.setFixedHeight(80)
        header.setStyleSheet("background-color: #2a2a2a;")
        hdr_layout = QHBoxLayout(header)
        hdr_layout.setContentsMargins(16, 0, 16, 0)

        back_btn = QPushButton("< Back")
        back_btn.setMinimumSize(140, 58)
        back_btn.setStyleSheet("""
            QPushButton { background-color: #555; font-size: 22px; }
            QPushButton:hover { background-color: #666; }
            QPushButton:pressed { background-color: #444; }
        """)
        back_btn.clicked.connect(self.back_requested.emit)
        hdr_layout.addWidget(back_btn)

        title = QLabel("Camera Settings")
        title.setFont(QFont("Arial", 26, QFont.Weight.Bold))
        title.setStyleSheet("color: white; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr_layout.addWidget(title, stretch=1)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setMinimumSize(130, 58)
        self._refresh_btn.setStyleSheet("""
            QPushButton { background-color: #34495e; font-size: 20px; }
            QPushButton:hover { background-color: #2c3e50; }
            QPushButton:pressed { background-color: #1a252f; }
        """)
        self._refresh_btn.clicked.connect(self.refresh)
        hdr_layout.addWidget(self._refresh_btn)

        outer.addWidget(header)

        # Scrollable body
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        body = QWidget()
        self._body_layout = QVBoxLayout(body)
        self._body_layout.setContentsMargins(40, 20, 40, 20)
        self._body_layout.setSpacing(10)

        self._no_camera_label = QLabel(
            "No gphoto2 camera connected.\n\n"
            "Switch to gphoto2 mode in Settings and replug the camera."
        )
        self._no_camera_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_camera_label.setStyleSheet("color: #888; font-size: 20px;")
        self._no_camera_label.setWordWrap(True)
        self._body_layout.addWidget(self._no_camera_label)

        # Settings group (populated dynamically)
        self._group = QGroupBox("Camera Controls")
        self._grid = QGridLayout(self._group)
        self._grid.setSpacing(14)
        self._grid.setColumnStretch(1, 1)
        self._body_layout.addWidget(self._group)
        self._group.hide()

        self._body_layout.addStretch()

        # Status + Apply bar
        bar = QWidget()
        bar.setFixedHeight(80)
        bar.setStyleSheet("background-color: #2a2a2a;")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(24, 0, 24, 0)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: #aaa; font-size: 16px;")
        bar_layout.addWidget(self._status_label, stretch=1)

        self._apply_btn = QPushButton("Apply Changes")
        self._apply_btn.setMinimumSize(220, 58)
        self._apply_btn.setStyleSheet("""
            QPushButton { background-color: #27ae60; font-size: 20px; font-weight: bold; }
            QPushButton:hover { background-color: #2ecc71; }
            QPushButton:pressed { background-color: #1e8449; }
            QPushButton:disabled { background-color: #333; color: #666; }
        """)
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self._apply_changes)
        bar_layout.addWidget(self._apply_btn)

        scroll.setWidget(body)
        outer.addWidget(scroll, stretch=1)
        outer.addWidget(bar)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_settings(self):
        settings = self._camera.get_camera_settings()

        # Clear previous widgets
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._widgets.clear()

        if not settings:
            self._group.hide()
            self._no_camera_label.show()
            self._apply_btn.setEnabled(False)
            self._status_label.setText("No settings available.")
            return

        self._no_camera_label.hide()
        self._group.show()

        row = 0
        for s in settings:
            label = QLabel(s["label"] + ":")
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self._grid.addWidget(label, row, 0)

            if s["type"] == "menu":
                combo = QComboBox()
                combo.setMinimumWidth(320)
                combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
                for choice in s["choices"]:
                    combo.addItem(str(choice), choice)
                idx = combo.findData(s["value"])
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                if s.get("readonly"):
                    combo.setEnabled(False)
                combo.currentIndexChanged.connect(
                    lambda _idx, name=s["name"], cb=combo:
                        self._on_changed(name, cb.currentData())
                )
                self._grid.addWidget(combo, row, 1)
                self._widgets[s["name"]] = combo

            elif s["type"] == "range":
                spin = QDoubleSpinBox()
                spin.setRange(s["min"], s["max"])
                spin.setSingleStep(s["step"])
                spin.setValue(float(s["value"]))
                spin.setMinimumWidth(180)
                if s.get("readonly"):
                    spin.setEnabled(False)
                spin.valueChanged.connect(
                    lambda val, name=s["name"]:
                        self._on_changed(name, str(val))
                )
                self._grid.addWidget(spin, row, 1)
                self._widgets[s["name"]] = spin

            row += 1

        self._status_label.setText(f"{len(settings)} settings loaded.")
        self._apply_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Changes
    # ------------------------------------------------------------------

    def _on_changed(self, name: str, value):
        self._pending[name] = value
        self._apply_btn.setEnabled(True)
        self._status_label.setText(f"{len(self._pending)} unsaved change(s).")

    def _apply_changes(self):
        if not self._pending:
            return

        self._apply_btn.setEnabled(False)
        self._status_label.setText("Applying…")

        failed = []
        for name, value in list(self._pending.items()):
            ok = self._camera.set_camera_setting(name, value)
            if ok:
                del self._pending[name]
            else:
                failed.append(name)

        if failed:
            self._status_label.setText(f"Failed to apply: {', '.join(failed)}")
            self._apply_btn.setEnabled(True)
        else:
            self._status_label.setText("All changes applied.")
            self._apply_btn.setEnabled(False)
