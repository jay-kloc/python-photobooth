"""Photobooth PyQt6 UI — fullscreen kiosk-style interface."""

import logging
from pathlib import Path

from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve, QRect, pyqtProperty,
    pyqtSignal, QThread,
)
from PyQt6.QtGui import (
    QImage, QPixmap, QFont, QKeyEvent, QPainter, QColor, QPen,
)
from PyQt6.QtWidgets import (
    QMainWindow, QLabel, QVBoxLayout, QWidget, QPushButton, QHBoxLayout,
    QGraphicsOpacityEffect, QStackedWidget, QMessageBox,
)

import cv2
import numpy as np

from src.camera import Camera, MockCamera, create_camera
from src.banner import has_banner, has_frame_overlay, render_banner_on_frame, stamp_banner_on_photo
from src.config import settings, WINDOW_WIDTH, WINDOW_HEIGHT, FULLSCREEN
from src.menu import MainMenu
from src.settings_panel import SettingsPanel
from src.camera_panel import CameraPanel
from src.gallery import GalleryPanel

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


class _CaptureWorker(QThread):
    """Runs camera.capture() off the main thread to avoid UI freezes."""

    done = pyqtSignal(object)   # emits Path on success, Exception on failure, None on soft-fail

    def __init__(self, camera, parent=None):
        super().__init__(parent)
        self._camera = camera

    def run(self):
        try:
            result = self._camera.capture()
        except Exception as exc:
            self.done.emit(exc)
        else:
            self.done.emit(result)


class PhotoboothScreen(QWidget):
    """Photobooth screen — camera preview, countdown, capture."""

    back_requested = pyqtSignal()
    camera_settings_requested = pyqtSignal()

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

    _BAR_H = 120  # height of the overlaid bottom control bar

    def _setup_ui(self):
        self.setStyleSheet("background-color: #000;")

        # Preview fills the entire widget — positioned in resizeEvent
        self._preview_label = QLabel(self)
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setStyleSheet("background-color: #000;")

        # Animated countdown overlay (covers preview area only)
        self._countdown_label = AnimatedCountdownLabel(self)
        self._countdown_label.hide()

        # Error overlay
        self._error_label = QLabel(self)
        self._error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._error_label.setWordWrap(True)
        self._error_label.setStyleSheet("""
            background-color: rgba(180, 30, 30, 210);
            color: white;
            font-size: 28px;
            font-weight: bold;
            border-radius: 16px;
            padding: 20px;
        """)
        self._error_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._error_label.hide()

        self._error_timer = QTimer(self)
        self._error_timer.setSingleShot(True)
        self._error_timer.timeout.connect(self._error_label.hide)

        # Flash overlay
        self._flash_overlay = FlashOverlay(self)

        # Semi-transparent bottom control bar overlaid on the preview
        self._bottom_bar = QWidget(self)
        self._bottom_bar.setStyleSheet("background-color: rgba(0, 0, 0, 170);")
        bar = QHBoxLayout(self._bottom_bar)
        bar.setContentsMargins(16, 8, 16, 8)
        bar.setSpacing(0)

        # Left section (stretch=1): MENU button
        left_widget = QWidget()
        left_widget.setStyleSheet("background: transparent;")
        left = QHBoxLayout(left_widget)
        left.setContentsMargins(0, 0, 0, 0)

        self._back_btn = QPushButton("MENU")
        self._back_btn.setMinimumSize(120, 70)
        self._back_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(80, 80, 80, 200);
                color: white;
                font-size: 20px;
                font-weight: bold;
                border: none;
                border-radius: 12px;
            }
            QPushButton:hover { background-color: rgba(100, 100, 100, 220); }
            QPushButton:pressed { background-color: rgba(60, 60, 60, 220); }
        """)
        self._back_btn.clicked.connect(self.back_requested.emit)
        left.addWidget(self._back_btn)
        left.addStretch()

        bar.addWidget(left_widget, stretch=1)

        # Center section: TAKE PHOTO button
        self._capture_btn = QPushButton("TAKE PHOTO")
        self._capture_btn.setMinimumSize(360, 108)
        self._capture_btn.setStyleSheet("""
            QPushButton {
                background-color: #e67e22;
                color: white;
                font-size: 30px;
                font-weight: bold;
                border: none;
                border-radius: 14px;
                margin: 0 16px;
            }
            QPushButton:hover { background-color: #d35400; }
            QPushButton:pressed { background-color: #ba4a00; }
            QPushButton:disabled { background-color: rgba(80, 80, 80, 180); color: #888; }
        """)
        self._capture_btn.clicked.connect(self._start_countdown)
        bar.addWidget(self._capture_btn)

        self._new_photo_btn = QPushButton("NEW PHOTO")
        self._new_photo_btn.setMinimumSize(360, 108)
        self._new_photo_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                font-size: 30px;
                font-weight: bold;
                border: none;
                border-radius: 14px;
                margin: 0 16px;
            }
            QPushButton:hover { background-color: #2ecc71; }
            QPushButton:pressed { background-color: #1e8449; }
        """)
        self._new_photo_btn.clicked.connect(self._return_to_live)
        self._new_photo_btn.hide()
        bar.addWidget(self._new_photo_btn)

        # Right section (stretch=1): counter + CAMERA button
        right_widget = QWidget()
        right_widget.setStyleSheet("background: transparent;")
        right = QHBoxLayout(right_widget)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(12)

        self._counter_label = QLabel("Photos: 0")
        self._counter_label.setStyleSheet("color: #bbb; font-size: 18px; background: transparent;")
        self._counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._counter_label.setMinimumWidth(110)
        right.addWidget(self._counter_label, stretch=1)

        self._cam_settings_btn = QPushButton("CAMERA")
        self._cam_settings_btn.setMinimumSize(120, 70)
        self._cam_settings_btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(44, 62, 80, 200);
                color: white;
                font-size: 17px;
                font-weight: bold;
                border: none;
                border-radius: 12px;
            }
            QPushButton:hover { background-color: rgba(52, 73, 94, 220); }
            QPushButton:pressed { background-color: rgba(26, 37, 47, 220); }
        """)
        self._cam_settings_btn.clicked.connect(self.camera_settings_requested.emit)
        right.addWidget(self._cam_settings_btn)

        bar.addWidget(right_widget, stretch=1)

    def _setup_timers(self):
        self._preview_timer = QTimer()
        self._preview_timer.timeout.connect(self._update_preview)

        self._countdown_timer = QTimer()
        self._countdown_timer.timeout.connect(self._countdown_tick)

    def start(self):
        """Activate the photobooth screen."""
        self._active = True
        self._state = self.STATE_LIVE
        self._capture_btn.setEnabled(True)
        self._countdown_label.hide()
        self._countdown_label.setText("")
        self._preview_timer.start(33)

    def stop(self):
        """Deactivate the photobooth screen."""
        self._active = False
        self._preview_timer.stop()
        self._countdown_timer.stop()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._reposition_overlays()

    def _reposition_overlays(self):
        W, H = self.width(), self.height()
        bar_h = self._BAR_H

        # Preview fills entire widget
        if hasattr(self, '_preview_label'):
            self._preview_label.setGeometry(0, 0, W, H)

        # Bottom bar overlaid at the bottom
        if hasattr(self, '_bottom_bar'):
            self._bottom_bar.setGeometry(0, H - bar_h, W, bar_h)
            self._bottom_bar.raise_()

        # Countdown covers the preview area (above the bar)
        if hasattr(self, '_countdown_label'):
            self._countdown_label.setGeometry(0, 0, W, H - bar_h)
            self._countdown_label.raise_()

        # Error overlay centered in the preview area
        if hasattr(self, '_error_label') and not self._error_label.isHidden():
            ew = min(W - 80, 700)
            eh = 160
            self._error_label.setGeometry(
                (W - ew) // 2,
                (H - bar_h - eh) // 2,
                ew, eh,
            )
            self._error_label.raise_()

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
        self._preview_timer.stop()
        self._reposition_overlays()

        # Start capture immediately — drain + trigger happens inside the worker
        self._capture_worker = _CaptureWorker(self._camera, self)
        self._capture_worker.done.connect(self._on_capture_done)
        self._capture_worker.start()

        self._capture_timeout = QTimer(self)
        self._capture_timeout.setSingleShot(True)
        self._capture_timeout.timeout.connect(self._on_capture_timeout)
        self._capture_timeout.start(15_000)

        # Visual white flash delayed 1.5 s to coincide with the camera flash firing
        # (Canon pre-metering takes ~1–1.5 s before the actual shutter/flash)
        QTimer.singleShot(1000, self._flash_overlay.flash)

    def _on_capture_done(self, result):
        self._capture_timeout.stop()

        if isinstance(result, Exception):
            logger.error("Capture raised an exception: %s", result)
            self._show_error(f"Capture error\n{result}")
            self._return_to_live()
            return

        filepath = result
        if filepath and filepath.exists():
            try:
                stamp_banner_on_photo(filepath)
            except Exception as e:
                logger.error("Banner stamp failed: %s", e)

            self._photo_count += 1
            self._counter_label.setText(f"Photos: {self._photo_count}")
            logger.info("Photo captured: %s", filepath)

            self._state = self.STATE_REVIEW
            self._capture_btn.hide()
            self._new_photo_btn.show()
            img = cv2.imread(str(filepath))
            if img is not None:
                self._display_frame(img)
        else:
            logger.error("Capture failed")
            self._show_error("Capture failed\nCheck the camera and try again")
            self._return_to_live()

    def _on_capture_timeout(self):
        logger.error("Capture timed out after 15 s")
        self._show_error("Camera not responding\nReplug the USB cable and try again")
        self._return_to_live()
        # Worker thread is still blocked in gphoto2 — nothing we can do but abandon it

    def _return_to_live(self):
        self._state = self.STATE_LIVE
        self._new_photo_btn.hide()
        self._capture_btn.show()
        self._capture_btn.setEnabled(True)
        self._preview_timer.start(33)  # resume liveview

    def _show_error(self, message: str, duration_ms: int = 3500):
        self._error_timer.stop()
        self._error_label.setText(message)
        self._error_label.show()
        self._reposition_overlays()
        self._error_timer.start(duration_ms)

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
    SCREEN_CAMERA = 3
    SCREEN_GALLERY = 4

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
        self._menu.open_gallery.connect(self._show_gallery)
        self._menu.open_settings.connect(self._show_settings)
        self._stack.addWidget(self._menu)

        # Photobooth screen
        self._photobooth = PhotoboothScreen(camera)
        self._photobooth.back_requested.connect(self._show_menu)
        self._photobooth.camera_settings_requested.connect(self._show_camera_settings)
        self._stack.addWidget(self._photobooth)

        # Settings screen
        self._settings = SettingsPanel()
        self._settings.back_requested.connect(self._show_menu)
        self._settings.camera_mode_changed.connect(self._reconnect_camera)
        self._stack.addWidget(self._settings)

        # Camera settings screen
        self._camera_panel = CameraPanel(camera)
        self._camera_panel.back_requested.connect(self._show_photobooth)
        self._stack.addWidget(self._camera_panel)

        # Gallery screen
        self._gallery = GalleryPanel()
        self._gallery.back_requested.connect(self._show_menu)
        self._stack.addWidget(self._gallery)

        # Start at menu
        self._stack.setCurrentIndex(self.SCREEN_MENU)

        if FULLSCREEN:
            self.showFullScreen()

    def _show_menu(self):
        self._photobooth.stop()
        self._stack.setCurrentIndex(self.SCREEN_MENU)

    def _show_photobooth(self):
        self._stack.setCurrentIndex(self.SCREEN_PHOTOBOOTH)
        if not self._photobooth._active:
            self._photobooth.start()

    def _show_settings(self):
        self._stack.setCurrentIndex(self.SCREEN_SETTINGS)

    def _show_camera_settings(self):
        self._photobooth.stop()
        self._camera_panel.set_camera(self._camera)
        self._stack.setCurrentIndex(self.SCREEN_CAMERA)
        self._camera_panel.refresh()

    def _show_gallery(self):
        self._gallery.refresh()
        self._stack.setCurrentIndex(self.SCREEN_GALLERY)

    def _reconnect_camera(self):
        """Close current camera and open a new one with the updated mode."""
        self._photobooth.stop()
        self._camera.close()
        self._camera = create_camera(settings.camera_mode)
        try:
            self._camera.open()
        except Exception as e:
            logger.error("Failed to open camera: %s", e)
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("Camera Error")
            msg.setText(str(e))
            msg.setInformativeText("Falling back to mock camera mode.")
            msg.exec()
            self._camera = MockCamera()
            self._camera.open()
        self._photobooth.set_camera(self._camera)
        self._camera_panel.set_camera(self._camera)
        logger.info("Camera reconnected in mode: %s", settings.camera_mode)

    def keyPressEvent(self, event: QKeyEvent):
        current = self._stack.currentIndex()
        if event.key() == Qt.Key.Key_Escape:
            if current == self.SCREEN_MENU:
                self.close()
            elif current == self.SCREEN_GALLERY:
                self._gallery.keyPressEvent(event)
                return
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
