"""Settings panel for configuring the photobooth."""

import logging
from pathlib import Path

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QSpinBox, QCheckBox, QFileDialog, QScrollArea, QFrame,
    QColorDialog, QGroupBox,
)

from src.config import settings
from src.banner import clear_cache as clear_banner_cache

logger = logging.getLogger(__name__)


class ColorButton(QPushButton):
    """A button that shows a color and opens a color picker on click."""

    color_changed = pyqtSignal(str)

    def __init__(self, initial_color: str, with_alpha: bool = False, parent=None):
        super().__init__(parent)
        self._with_alpha = with_alpha
        self._color = initial_color
        self.setMinimumSize(80, 50)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()
        self.clicked.connect(self._pick_color)

    def _update_style(self):
        parsed = self._color.lstrip("#")
        display = parsed[:6] if len(parsed) >= 6 else parsed
        self.setStyleSheet(
            f"background-color: #{display}; border: 2px solid #555; border-radius: 4px;"
        )

    def _pick_color(self):
        parsed = self._color.lstrip("#")[:6]
        initial = QColor(f"#{parsed}")
        color = QColorDialog.getColor(initial, self, "Pick Color")
        if color.isValid():
            hex_color = color.name()
            if self._with_alpha and len(self._color.lstrip("#")) == 8:
                # Preserve existing alpha
                hex_color += self._color.lstrip("#")[6:8]
            self._color = hex_color
            self._update_style()
            self.color_changed.emit(self._color)

    def get_color(self) -> str:
        return self._color


class SettingsPanel(QWidget):
    """Settings panel with banner customization."""

    back_requested = pyqtSignal()
    camera_mode_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._load_current_settings()

    def _setup_ui(self):
        self.setStyleSheet("""
            QWidget { background-color: #1a1a1a; color: #eee; }
            QGroupBox {
                font-size: 20px; font-weight: bold; color: #fff;
                border: 2px solid #444; border-radius: 10px;
                margin-top: 20px; padding-top: 24px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 16px; padding: 0 8px;
            }
            QLabel { font-size: 18px; color: #ccc; }
            QLineEdit {
                font-size: 18px; padding: 12px; min-height: 28px;
                border: 2px solid #555;
                border-radius: 8px; background: #2a2a2a; color: #fff;
            }
            QLineEdit:focus { border-color: #3498db; }
            QComboBox {
                font-size: 18px; padding: 10px; min-height: 28px;
                border: 2px solid #555;
                border-radius: 8px; background: #2a2a2a; color: #fff;
            }
            QComboBox::drop-down { width: 40px; }
            QComboBox QAbstractItemView { font-size: 18px; min-height: 40px; }
            QSpinBox {
                font-size: 18px; padding: 10px; min-height: 28px;
                border: 2px solid #555;
                border-radius: 8px; background: #2a2a2a; color: #fff;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                width: 36px;
            }
            QCheckBox { font-size: 18px; spacing: 12px; }
            QCheckBox::indicator { width: 32px; height: 32px; }
            QPushButton {
                font-size: 18px; padding: 14px 24px; border: none;
                border-radius: 10px; color: white;
            }
            QScrollBar:vertical {
                width: 20px; background: #2a2a2a; border-radius: 10px;
            }
            QScrollBar::handle:vertical {
                background: #666; border-radius: 10px; min-height: 60px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
        """)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        # Header bar
        header = QWidget()
        header.setFixedHeight(80)
        header.setStyleSheet("background-color: #2a2a2a;")
        header_layout = QHBoxLayout(header)

        self._back_btn = QPushButton("< Back")
        self._back_btn.setMinimumSize(140, 60)
        self._back_btn.setStyleSheet("""
            QPushButton { background-color: #555; font-size: 22px; }
            QPushButton:hover { background-color: #666; }
            QPushButton:pressed { background-color: #444; }
        """)
        self._back_btn.clicked.connect(self._on_back)
        header_layout.addWidget(self._back_btn)

        title = QLabel("Settings")
        title.setFont(QFont("Arial", 28, QFont.Weight.Bold))
        title.setStyleSheet("color: white;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(title, stretch=1)

        outer_layout.addWidget(header)

        # Scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setSpacing(10)
        layout.setContentsMargins(40, 20, 40, 40)

        # --- Event Banner Group ---
        banner_group = QGroupBox("Event Banner")
        banner_layout = QVBoxLayout(banner_group)
        banner_layout.setSpacing(12)

        # Event name
        row = QHBoxLayout()
        row.addWidget(QLabel("Event Name:"))
        self._event_name_input = QLineEdit()
        self._event_name_input.setPlaceholderText("e.g. Sarah & Tom's Wedding")
        row.addWidget(self._event_name_input, stretch=1)
        banner_layout.addLayout(row)

        # Event date
        row = QHBoxLayout()
        row.addWidget(QLabel("Event Date:"))
        self._event_date_input = QLineEdit()
        self._event_date_input.setPlaceholderText("e.g. April 12, 2026")
        row.addWidget(self._event_date_input, stretch=1)
        banner_layout.addLayout(row)

        # Logo
        row = QHBoxLayout()
        row.addWidget(QLabel("Logo Image:"))
        self._logo_path_input = QLineEdit()
        self._logo_path_input.setPlaceholderText("Path to PNG image (optional)")
        row.addWidget(self._logo_path_input, stretch=1)
        self._logo_browse_btn = QPushButton("Browse")
        self._logo_browse_btn.setMinimumSize(110, 50)
        self._logo_browse_btn.setStyleSheet("""
            QPushButton { background-color: #3498db; }
            QPushButton:hover { background-color: #2980b9; }
            QPushButton:pressed { background-color: #2471a3; }
        """)
        self._logo_browse_btn.clicked.connect(self._browse_logo)
        row.addWidget(self._logo_browse_btn)
        self._logo_clear_btn = QPushButton("Clear")
        self._logo_clear_btn.setMinimumSize(90, 50)
        self._logo_clear_btn.setStyleSheet("""
            QPushButton { background-color: #e74c3c; }
            QPushButton:hover { background-color: #c0392b; }
            QPushButton:pressed { background-color: #a93226; }
        """)
        self._logo_clear_btn.clicked.connect(lambda: self._logo_path_input.clear())
        row.addWidget(self._logo_clear_btn)
        banner_layout.addLayout(row)

        # Logo preview
        self._logo_preview = QLabel()
        self._logo_preview.setFixedHeight(80)
        self._logo_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._logo_preview.setStyleSheet("background: #2a2a2a; border-radius: 4px;")
        banner_layout.addWidget(self._logo_preview)
        self._logo_path_input.textChanged.connect(self._update_logo_preview)

        # Banner position
        row = QHBoxLayout()
        row.addWidget(QLabel("Position:"))
        self._position_combo = QComboBox()
        self._position_combo.addItems(["bottom", "top"])
        self._position_combo.setMinimumWidth(200)
        row.addWidget(self._position_combo)
        row.addStretch()
        banner_layout.addLayout(row)

        # Font size
        row = QHBoxLayout()
        row.addWidget(QLabel("Font Size:"))
        self._font_size_spin = QSpinBox()
        self._font_size_spin.setRange(12, 120)
        self._font_size_spin.setSuffix(" px")
        self._font_size_spin.setMinimumWidth(160)
        row.addWidget(self._font_size_spin)
        row.addStretch()
        banner_layout.addLayout(row)

        # Text color
        row = QHBoxLayout()
        row.addWidget(QLabel("Text Color:"))
        self._text_color_btn = ColorButton("#ffffff")
        row.addWidget(self._text_color_btn)
        row.addStretch()
        banner_layout.addLayout(row)

        # Background color
        row = QHBoxLayout()
        row.addWidget(QLabel("Background:"))
        self._bg_color_btn = ColorButton("#000000aa", with_alpha=True)
        row.addWidget(self._bg_color_btn)
        bg_alpha_label = QLabel("  Alpha:")
        row.addWidget(bg_alpha_label)
        self._bg_alpha_spin = QSpinBox()
        self._bg_alpha_spin.setRange(0, 255)
        self._bg_alpha_spin.setMinimumWidth(140)
        row.addWidget(self._bg_alpha_spin)
        row.addStretch()
        banner_layout.addLayout(row)

        # Stamp on photo
        self._stamp_check = QCheckBox("Stamp banner and frame on saved photos")
        banner_layout.addWidget(self._stamp_check)

        # Frame overlay
        frame_label = QLabel("Frame Overlay")
        frame_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #fff; margin-top: 10px;")
        banner_layout.addWidget(frame_label)
        frame_desc = QLabel("PNG image with transparent center — overlaid on top of photos")
        frame_desc.setStyleSheet("font-size: 12px; color: #888;")
        banner_layout.addWidget(frame_desc)

        row = QHBoxLayout()
        self._frame_path_input = QLineEdit()
        self._frame_path_input.setPlaceholderText("Path to frame PNG (optional)")
        row.addWidget(self._frame_path_input, stretch=1)
        self._frame_browse_btn = QPushButton("Browse")
        self._frame_browse_btn.setMinimumSize(110, 50)
        self._frame_browse_btn.setStyleSheet("""
            QPushButton { background-color: #3498db; }
            QPushButton:hover { background-color: #2980b9; }
            QPushButton:pressed { background-color: #2471a3; }
        """)
        self._frame_browse_btn.clicked.connect(self._browse_frame)
        row.addWidget(self._frame_browse_btn)
        self._frame_clear_btn = QPushButton("Clear")
        self._frame_clear_btn.setMinimumSize(90, 50)
        self._frame_clear_btn.setStyleSheet("""
            QPushButton { background-color: #e74c3c; }
            QPushButton:hover { background-color: #c0392b; }
            QPushButton:pressed { background-color: #a93226; }
        """)
        self._frame_clear_btn.clicked.connect(lambda: self._frame_path_input.clear())
        row.addWidget(self._frame_clear_btn)
        banner_layout.addLayout(row)

        # Frame preview
        self._frame_preview = QLabel()
        self._frame_preview.setFixedHeight(120)
        self._frame_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._frame_preview.setStyleSheet("background: #2a2a2a; border-radius: 4px;")
        banner_layout.addWidget(self._frame_preview)
        self._frame_path_input.textChanged.connect(self._update_frame_preview)

        layout.addWidget(banner_group)

        # --- Photobooth Settings Group ---
        booth_group = QGroupBox("Photobooth")
        booth_layout = QVBoxLayout(booth_group)
        booth_layout.setSpacing(12)

        # Countdown
        row = QHBoxLayout()
        row.addWidget(QLabel("Countdown:"))
        self._countdown_spin = QSpinBox()
        self._countdown_spin.setRange(1, 10)
        self._countdown_spin.setSuffix(" seconds")
        self._countdown_spin.setMinimumWidth(180)
        row.addWidget(self._countdown_spin)
        row.addStretch()
        booth_layout.addLayout(row)

        # Review duration
        row = QHBoxLayout()
        row.addWidget(QLabel("Photo Review:"))
        self._review_spin = QSpinBox()
        self._review_spin.setRange(1, 30)
        self._review_spin.setSuffix(" seconds")
        self._review_spin.setMinimumWidth(180)
        row.addWidget(self._review_spin)
        row.addStretch()
        booth_layout.addLayout(row)

        layout.addWidget(booth_group)

        # --- Camera Group ---
        camera_group = QGroupBox("Camera")
        camera_layout = QVBoxLayout(camera_group)
        camera_layout.setSpacing(12)

        row = QHBoxLayout()
        row.addWidget(QLabel("Camera Mode:"))
        self._camera_mode_combo = QComboBox()
        self._camera_mode_combo.addItem("Mock (webcam / test pattern)", "mock")
        self._camera_mode_combo.addItem("Canon DSLR (gphoto2)", "gphoto2")
        self._camera_mode_combo.setMinimumWidth(320)
        row.addWidget(self._camera_mode_combo)
        row.addStretch()
        camera_layout.addLayout(row)

        camera_note = QLabel("Changing camera mode reconnects the camera immediately on save.")
        camera_note.setStyleSheet("font-size: 14px; color: #888;")
        camera_note.setWordWrap(True)
        camera_layout.addWidget(camera_note)

        layout.addWidget(camera_group)

        layout.addSpacing(20)

        # Save button at the bottom of the form
        save_row = QHBoxLayout()
        save_row.addStretch()
        self._save_btn = QPushButton("Save Settings")
        self._save_btn.setMinimumSize(300, 70)
        self._save_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60; font-size: 22px;
                font-weight: bold; border-radius: 12px;
            }
            QPushButton:hover { background-color: #2ecc71; }
            QPushButton:pressed { background-color: #1e8449; }
        """)
        self._save_btn.clicked.connect(self._save_settings)
        save_row.addWidget(self._save_btn)
        save_row.addStretch()
        layout.addLayout(save_row)

        layout.addStretch()
        scroll.setWidget(content)
        outer_layout.addWidget(scroll)

    def _load_current_settings(self):
        """Populate fields from current settings."""
        self._event_name_input.setText(settings.event_name)
        self._event_date_input.setText(settings.event_date)
        self._logo_path_input.setText(settings.event_logo)
        self._position_combo.setCurrentText(settings.banner_position)
        self._font_size_spin.setValue(settings.banner_font_size)
        self._text_color_btn._color = settings.banner_color
        self._text_color_btn._update_style()
        self._bg_color_btn._color = settings.banner_bg_color[:7] if len(settings.banner_bg_color) > 7 else settings.banner_bg_color
        self._bg_color_btn._update_style()
        # Parse alpha from bg color
        bg_hex = settings.banner_bg_color.lstrip("#")
        alpha = int(bg_hex[6:8], 16) if len(bg_hex) == 8 else 170
        self._bg_alpha_spin.setValue(alpha)
        self._stamp_check.setChecked(settings.stamp_on_photo)
        self._frame_path_input.setText(settings.frame_overlay)
        self._update_frame_preview()
        self._countdown_spin.setValue(settings.countdown_seconds)
        self._review_spin.setValue(settings.preview_display_seconds)
        idx = self._camera_mode_combo.findData(settings.camera_mode)
        if idx >= 0:
            self._camera_mode_combo.setCurrentIndex(idx)
        self._update_logo_preview()

    def _browse_frame(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Frame Overlay", "",
            "PNG Images (*.png);;All Files (*)"
        )
        if path:
            self._frame_path_input.setText(path)

    def _update_frame_preview(self):
        path = self._frame_path_input.text().strip()
        if path and Path(path).exists():
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                scaled = pixmap.scaled(
                    200, 110,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._frame_preview.setPixmap(scaled)
                return
        self._frame_preview.clear()
        self._frame_preview.setText("No frame selected" if not path else "File not found")

    def _browse_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Logo Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.svg);;All Files (*)"
        )
        if path:
            self._logo_path_input.setText(path)

    def _update_logo_preview(self):
        path = self._logo_path_input.text().strip()
        if path and Path(path).exists():
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                scaled = pixmap.scaledToHeight(
                    70, Qt.TransformationMode.SmoothTransformation
                )
                self._logo_preview.setPixmap(scaled)
                return
        self._logo_preview.clear()
        self._logo_preview.setText("No logo selected" if not path else "File not found")

    def _save_settings(self):
        """Apply and persist settings."""
        settings.set("event_name", self._event_name_input.text().strip())
        settings.set("event_date", self._event_date_input.text().strip())
        settings.set("event_logo", self._logo_path_input.text().strip())
        settings.set("banner_position", self._position_combo.currentText())
        settings.set("banner_font_size", self._font_size_spin.value())
        settings.set("banner_color", self._text_color_btn.get_color())

        # Compose bg color with alpha
        bg_hex = self._bg_color_btn.get_color().lstrip("#")[:6]
        alpha_hex = format(self._bg_alpha_spin.value(), "02x")
        settings.set("banner_bg_color", f"#{bg_hex}{alpha_hex}")

        settings.set("stamp_on_photo", self._stamp_check.isChecked())
        settings.set("frame_overlay", self._frame_path_input.text().strip())
        settings.set("countdown_seconds", self._countdown_spin.value())
        settings.set("preview_display_seconds", self._review_spin.value())

        old_camera_mode = settings.camera_mode
        new_camera_mode = self._camera_mode_combo.currentData()
        settings.set("camera_mode", new_camera_mode)

        settings.save()
        clear_banner_cache()
        logger.info("Settings saved")

        if new_camera_mode != old_camera_mode:
            self.camera_mode_changed.emit()

        self._save_btn.setText("Saved!")
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(1500, lambda: self._save_btn.setText("Save Settings"))

    def _on_back(self):
        self.back_requested.emit()
