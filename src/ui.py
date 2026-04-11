"""Photobooth PyQt6 UI — fullscreen kiosk-style interface."""

import logging
from pathlib import Path

from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect, pyqtProperty,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QImage, QPixmap, QFont, QKeyEvent, QPainter, QColor, QPen,
)
from PyQt6.QtWidgets import (
    QMainWindow, QLabel, QVBoxLayout, QWidget, QPushButton, QHBoxLayout,
    QGraphicsOpacityEffect, QStackedWidget,
)

import cv2
import numpy as np

from src.camera import Camera, create_camera
from src.banner import has_banner, has_frame_overlay, render_banner_on_frame, stamp_banner_on_photo
from src.config import settings, WINDOW_WIDTH, WINDOW_HEIGHT, FULLSCREEN
from src.menu import MainMenu
from src.settings_panel import SettingsPanel

logger = logging.getLogger(__name__)


# Animation duration constants (ms)
COUNTDOWN_ANIM_DURATION = 800
FLASH_DURATION = 500


class AnimatedCountdownLabel(QLabel):
    """A label that animates countdown numbers with scale + fade."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._font_size = 200
        self._opacity = 1.0
        self._color = QColor(255, 255, 255)

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self._opacity_effect.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity_effect)

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def _get_font_size(self):
        return self._font_size

    def _set_font_size(self, size):
        self._font_size = int(size)
        self.update()

    fontSize = pyqtProperty(float, _get_font_size, _set_font_size)

    def _get_opacity(self):
        return self._opacity

    def _set_opacity(self, value):
        self._opacity = value
        self._opacity_effect.setOpacity(value)

    opacity = pyqtProperty(float, _get_opacity, _set_opacity)

    def paintEvent(self, event):
        if not self.text():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        font = QFont("Arial", self._font_size, QFont.Weight.Bold)
        painter.setFont(font)

        # Draw shadow
        shadow_color = QColor(0, 0, 0, 120)
        painter.setPen(QPen(shadow_color))
        shadow_rect = self.rect().adjusted(4, 4, 4, 4)
        painter.drawText(shadow_rect, Qt.AlignmentFlag.AlignCenter, self.text())

        # Draw main text
        painter.setPen(QPen(self._color))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())

        painter.end()

    def animate_number(self, number: int, on_finished=None):
        """Animate a number appearing large then shrinking with fade."""
        self.setText(str(number))

        # Pick color based on number
        if number <= 1:
            self._color = QColor(231, 76, 60)  # red
        elif number <= 2:
            self._color = QColor(241, 196, 15)  # yellow
        else:
            self._color = QColor(255, 255, 255)  # white

        # Font size animation: start big, shrink
        self._size_anim = QPropertyAnimation(self, b"fontSize")
        self._size_anim.setDuration(COUNTDOWN_ANIM_DURATION)
        self._size_anim.setStartValue(300)
        self._size_anim.setEndValue(120)
        self._size_anim.setEasingCurve(QEasingCurve.Type.OutBack)

        # Opacity animation: fade in then hold
        self._opacity_anim = QPropertyAnimation(self, b"opacity")
        self._opacity_anim.setDuration(COUNTDOWN_ANIM_DURATION)
        self._opacity_anim.setStartValue(0.0)
        self._opacity_anim.setKeyValueAt(0.15, 1.0)
        self._opacity_anim.setEndValue(0.9)

        if on_finished:
            self._size_anim.finished.connect(on_finished)

        self._size_anim.start()
        self._opacity_anim.start()

    def animate_go(self, on_finished=None):
        """Animate a 'Smile!' text that zooms in and fades out."""
        self.setText("Smile!")
        self._color = QColor(46, 204, 113)  # green

        self._size_anim = QPropertyAnimation(self, b"fontSize")
        self._size_anim.setDuration(400)
        self._size_anim.setStartValue(100)
        self._size_anim.setEndValue(350)
        self._size_anim.setEasingCurve(QEasingCurve.Type.OutQuad)

        self._opacity_anim = QPropertyAnimation(self, b"opacity")
        self._opacity_anim.setDuration(400)
        self._opacity_anim.setStartValue(1.0)
        self._opacity_anim.setEndValue(0.0)
        self._opacity_anim.setEasingCurve(QEasingCurve.Type.InQuad)

        if on_finished:
            self._opacity_anim.finished.connect(on_finished)

        self._size_anim.start()
        self._opacity_anim.start()


class FlashOverlay(QWidget):
    """Full-screen white flash effect that simulates a camera flash."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._alpha = 255
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(255, 255, 255, self._alpha))
        painter.end()

    def flash(self, on_finished=None):
        """Trigger the flash animation — solid white that fades out."""
        if self.parent():
            self.setGeometry(0, 0, self.parent().width(), self.parent().height())
        self._alpha = 255
        self._on_finished = on_finished
        self.show()
        self.raise_()
        self.update()

        self._flash_step = 0
        self._flash_steps = 15

        self._fade_timer = QTimer(self)
        self._fade_timer.setInterval(40)  # ~600ms total
        self._fade_timer.timeout.connect(self._fade_step)
        self._fade_timer.start()

    def _fade_step(self):
        """Gradually fade out the white overlay."""
        self._flash_step += 1
        if self._flash_step >= self._flash_steps:
            self._fade_timer.stop()
            self.hide()
            if self._on_finished:
                self._on_finished()
            return

        self._alpha = int(255 * (1.0 - self._flash_step / self._flash_steps))
        self.update()


class PhotoboothScreen(QWidget):
    """Photobooth screen — camera preview, countdown, capture."""

    back_requested = pyqtSignal()

    # States
    STATE_LIVE = "live"
    STATE_COUNTDOWN = "countdown"
    STATE_CAPTURE = "capture"
    STATE_REVIEW = "review"

    def __init__(self, camera: Camera, parent=None):
        super().__init__(parent)
        self._camera = camera
        self._state = self.STATE_LIVE
        self._countdown_remaining = 0
        self._photo_count = 0
        self._active = False

        self._setup_ui()
        self._setup_timers()

    def _setup_ui(self):
        self.setStyleSheet("background-color: #1a1a1a;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)

        # Camera preview / photo display
        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setStyleSheet("background-color: #000;")
        layout.addWidget(self._preview_label, stretch=1)

        # Animated countdown overlay
        self._countdown_label = AnimatedCountdownLabel(self)
        self._countdown_label.hide()

        # Flash overlay
        self._flash_overlay = FlashOverlay(self)

        # Bottom bar
        bottom = QHBoxLayout()
        bottom.setSpacing(20)

        self._back_btn = QPushButton("MENU")
        self._back_btn.setMinimumSize(120, 80)
        self._back_btn.setStyleSheet("""
            QPushButton {
                background-color: #555;
                color: white;
                font-size: 20px;
                font-weight: bold;
                border: none;
                border-radius: 12px;
            }
            QPushButton:hover { background-color: #666; }
            QPushButton:pressed { background-color: #444; }
        """)
        self._back_btn.clicked.connect(self.back_requested.emit)
        bottom.addWidget(self._back_btn)

        self._status_label = QLabel("Tap the button to take a photo")
        self._status_label.setStyleSheet("color: #aaa; font-size: 20px;")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bottom.addWidget(self._status_label, stretch=1)

        self._capture_btn = QPushButton("TAKE PHOTO")
        self._capture_btn.setMinimumSize(320, 100)
        self._capture_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                font-size: 28px;
                font-weight: bold;
                border: none;
                border-radius: 16px;
            }
            QPushButton:hover { background-color: #c0392b; }
            QPushButton:pressed { background-color: #a93226; }
            QPushButton:disabled { background-color: #555; color: #999; }
        """)
        self._capture_btn.clicked.connect(self._start_countdown)
        bottom.addWidget(self._capture_btn)

        self._counter_label = QLabel("Photos: 0")
        self._counter_label.setStyleSheet("color: #aaa; font-size: 20px;")
        self._counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._counter_label.setMinimumWidth(120)
        bottom.addWidget(self._counter_label)

        layout.addLayout(bottom)

    def _setup_timers(self):
        self._preview_timer = QTimer()
        self._preview_timer.timeout.connect(self._update_preview)

        self._countdown_timer = QTimer()
        self._countdown_timer.timeout.connect(self._countdown_tick)

        self._review_timer = QTimer()
        self._review_timer.setSingleShot(True)
        self._review_timer.timeout.connect(self._end_review)

    def start(self):
        """Activate the photobooth screen."""
        self._active = True
        self._state = self.STATE_LIVE
        self._preview_timer.start(33)

    def stop(self):
        """Deactivate the photobooth screen."""
        self._active = False
        self._preview_timer.stop()
        self._countdown_timer.stop()
        self._review_timer.stop()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_overlays()

    def _reposition_overlays(self):
        if hasattr(self, '_countdown_label'):
            self._countdown_label.setGeometry(self._preview_label.geometry())

    def _update_preview(self):
        if self._state not in (self.STATE_LIVE, self.STATE_COUNTDOWN):
            return

        frame = self._camera.get_preview_frame()
        if frame is None:
            return

        if has_banner() or has_frame_overlay():
            frame = render_banner_on_frame(frame)

        self._display_frame(frame)

    def _display_frame(self, frame: np.ndarray):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)

        scaled = pixmap.scaled(
            self._preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._preview_label.setPixmap(scaled)

    def _start_countdown(self):
        if self._state != self.STATE_LIVE:
            return

        self._state = self.STATE_COUNTDOWN
        self._countdown_remaining = settings.countdown_seconds
        self._capture_btn.setEnabled(False)
        self._status_label.setText("Get ready!")

        self._reposition_overlays()
        self._countdown_label.show()
        self._countdown_label.raise_()
        self._countdown_label.animate_number(self._countdown_remaining)
        self._countdown_timer.start(1000)

    def _countdown_tick(self):
        self._countdown_remaining -= 1
        if self._countdown_remaining <= 0:
            self._countdown_timer.stop()
            self._countdown_label.animate_go(on_finished=self._on_go_finished)
        else:
            self._countdown_label.animate_number(self._countdown_remaining)

    def _on_go_finished(self):
        QTimer.singleShot(500, self._on_smile_delay_finished)

    def _on_smile_delay_finished(self):
        self._countdown_label.hide()
        self._countdown_label.setText("")
        self._do_capture()

    def _do_capture(self):
        self._state = self.STATE_CAPTURE
        self._status_label.setText("Capturing...")

        self._reposition_overlays()
        self._flash_overlay.flash(on_finished=self._on_flash_finished)

    def _on_flash_finished(self):
        filepath = self._camera.capture()

        if filepath and filepath.exists():
            stamp_banner_on_photo(filepath)
            self._photo_count += 1
            self._counter_label.setText(f"Photos: {self._photo_count}")
            self._status_label.setText(f"Saved: {filepath.name}")
            logger.info("Photo captured: %s", filepath)

            self._state = self.STATE_REVIEW
            img = cv2.imread(str(filepath))
            if img is not None:
                self._display_frame(img)
            self._review_timer.start(settings.preview_display_seconds * 1000)
        else:
            self._status_label.setText("Capture failed!")
            logger.error("Capture failed")
            self._return_to_live()

    def _end_review(self):
        self._return_to_live()

    def _return_to_live(self):
        self._state = self.STATE_LIVE
        self._capture_btn.setEnabled(True)
        self._status_label.setText("Tap the button to take a photo")

    def set_camera(self, camera: Camera):
        """Swap the camera backend (called after settings change)."""
        self._camera = camera

    def handle_key(self, key):
        """Handle key press forwarded from the main window."""
        if key == Qt.Key.Key_Space:
            self._start_countdown()


class AppWindow(QMainWindow):
    """Main application window — manages menu, photobooth, and settings screens."""

    SCREEN_MENU = 0
    SCREEN_PHOTOBOOTH = 1
    SCREEN_SETTINGS = 2

    def __init__(self, camera: Camera):
        super().__init__()
        self._camera = camera

        self.setWindowTitle("Photobooth")
        self.setStyleSheet("background-color: #1a1a1a;")
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)

        # Stacked widget for screen switching
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        # Menu screen
        self._menu = MainMenu()
        self._menu.start_photobooth.connect(self._show_photobooth)
        self._menu.open_settings.connect(self._show_settings)
        self._stack.addWidget(self._menu)

        # Photobooth screen
        self._photobooth = PhotoboothScreen(camera)
        self._photobooth.back_requested.connect(self._show_menu)
        self._stack.addWidget(self._photobooth)

        # Settings screen
        self._settings = SettingsPanel()
        self._settings.back_requested.connect(self._show_menu)
        self._settings.camera_mode_changed.connect(self._reconnect_camera)
        self._stack.addWidget(self._settings)

        # Start at menu
        self._stack.setCurrentIndex(self.SCREEN_MENU)

        if FULLSCREEN:
            self.showFullScreen()

    def _show_menu(self):
        self._photobooth.stop()
        self._stack.setCurrentIndex(self.SCREEN_MENU)

    def _show_photobooth(self):
        self._stack.setCurrentIndex(self.SCREEN_PHOTOBOOTH)
        self._photobooth.start()

    def _show_settings(self):
        self._stack.setCurrentIndex(self.SCREEN_SETTINGS)

    def _reconnect_camera(self):
        """Close current camera and open a new one with the updated mode."""
        self._photobooth.stop()
        self._camera.close()
        self._camera = create_camera(settings.camera_mode)
        self._camera.open()
        self._photobooth.set_camera(self._camera)
        logger.info("Camera reconnected in mode: %s", settings.camera_mode)

    def keyPressEvent(self, event: QKeyEvent):
        current = self._stack.currentIndex()
        if event.key() == Qt.Key.Key_Escape:
            if current == self.SCREEN_MENU:
                self.close()
            else:
                self._show_menu()
        elif event.key() == Qt.Key.Key_F11:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()
        elif current == self.SCREEN_PHOTOBOOTH:
            self._photobooth.handle_key(event.key())

    def closeEvent(self, event):
        self._photobooth.stop()
        self._camera.close()
        event.accept()
