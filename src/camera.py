"""Camera abstraction with mock and gphoto2 backends."""

import abc
import time
import logging
from pathlib import Path
from datetime import datetime

import cv2
import numpy as np

from src.config import PHOTOS_DIR, settings

logger = logging.getLogger(__name__)


class Camera(abc.ABC):
    """Abstract camera interface."""

    @abc.abstractmethod
    def open(self):
        """Initialize the camera connection."""

    @abc.abstractmethod
    def close(self):
        """Release the camera connection."""

    @abc.abstractmethod
    def get_preview_frame(self) -> np.ndarray | None:
        """Return a preview frame as a BGR numpy array, or None on failure."""

    @abc.abstractmethod
    def capture(self) -> Path | None:
        """Capture a full-resolution photo. Returns the saved file path."""

    def get_camera_settings(self) -> list[dict]:
        """Return a list of adjustable camera settings.

        Each dict has keys: name, label, value, type ('menu' or 'range'),
        and either 'choices' (list) or 'min'/'max'/'step' (floats).
        """
        return []

    def set_camera_setting(self, name: str, value: str) -> bool:
        """Apply a single camera setting by name. Returns True on success."""
        return False

    def _generate_filename(self, ext: str = "jpg") -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return PHOTOS_DIR / f"{settings.photo_prefix}_{timestamp}.{ext}"


class MockCamera(Camera):
    """Mock camera using the system webcam via OpenCV (for development)."""

    def __init__(self):
        self._cap = None

    def open(self):
        self._cap = cv2.VideoCapture(0)
        if not self._cap.isOpened():
            logger.warning("No webcam found — using generated test frames")
            self._cap = None

    def close(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def get_preview_frame(self) -> np.ndarray | None:
        if self._cap is not None:
            ret, frame = self._cap.read()
            return frame if ret else None
        # Generate a test pattern if no webcam
        return self._generate_test_frame()

    def capture(self) -> Path | None:
        frame = self.get_preview_frame()
        if frame is None:
            return None
        filepath = self._generate_filename()
        cv2.imwrite(str(filepath), frame)
        logger.info("Mock capture saved to %s", filepath)
        return filepath

    @staticmethod
    def _generate_test_frame() -> np.ndarray:
        """Generate a color test pattern with timestamp."""
        frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        # Gradient background
        for i in range(720):
            frame[i, :, 0] = int(255 * i / 720)  # blue gradient
            frame[i, :, 2] = int(255 * (720 - i) / 720)  # red gradient
        # Add timestamp text
        text = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        cv2.putText(frame, text, (400, 380), cv2.FONT_HERSHEY_SIMPLEX,
                    2.0, (255, 255, 255), 3)
        cv2.putText(frame, "MOCK CAMERA", (420, 450), cv2.FONT_HERSHEY_SIMPLEX,
                    1.0, (200, 200, 200), 2)
        return frame


class GPhotoCamera(Camera):
    """Real DSLR camera via libgphoto2."""

    def __init__(self):
        self._camera = None

    def open(self):
        import gphoto2 as gp
        self._camera = gp.Camera()
        try:
            self._camera.init()
        except gp.GPhoto2Error as e:
            if e.code == -53:  # GP_ERROR_IO_USB_CLAIM — gvfs has the device
                logger.warning("Camera claimed by another process (gvfs), attempting to release it...")
                import subprocess, time
                subprocess.run(["pkill", "-f", "gvfsd-gphoto2"], capture_output=True)
                time.sleep(1.5)
                self._camera.init()  # raises if still fails
            elif e.code == -105:  # GP_ERROR_MODEL_NOT_FOUND — wrong USB mode
                self._camera = None
                raise RuntimeError(
                    "Camera not recognized by gphoto2.\n\n"
                    "On your Canon camera, go to:\n"
                    "  Menu → Communication / PC Connection → PTP\n"
                    "(not 'Mass Storage' or 'MTP')\n\n"
                    "Then replug the USB cable and try again."
                ) from e
            else:
                raise
        logger.info("GPhoto2 camera connected: %s",
                     self._camera.get_summary().text[:80])

    def close(self):
        if self._camera is not None:
            self._camera.exit()
            self._camera = None

    def get_preview_frame(self) -> np.ndarray | None:
        import gphoto2 as gp
        if self._camera is None:
            return None
        try:
            capture = self._camera.capture_preview()
            data = capture.get_data_and_size()
            buf = np.frombuffer(data, dtype=np.uint8)
            frame = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            return frame
        except gp.GPhoto2Error as e:
            logger.error("Preview error: %s", e)
            return None

    def capture(self) -> Path | None:
        import gphoto2 as gp
        if self._camera is None:
            return None
        try:
            file_path = self._camera.capture(gp.GP_CAPTURE_IMAGE)
            target = self._generate_filename()
            camera_file = self._camera.file_get(
                file_path.folder, file_path.name, gp.GP_FILE_TYPE_NORMAL
            )
            camera_file.save(str(target))
            logger.info("GPhoto2 capture saved to %s", target)
            return target
        except gp.GPhoto2Error as e:
            logger.error("Capture error: %s", e)
            return None

    # Settings to expose, in display order
    _SETTINGS_NAMES = [
        "iso",
        "shutterspeed",
        "aperture",
        "whitebalance",
        "exposurecompensation",
        "imageformat",
        "drivemode",
        "meteringmode",
        "picturestyle",
        "colorspace",
        "focusmode",
        "capturetarget",
    ]

    def get_camera_settings(self) -> list[dict]:
        import gphoto2 as gp
        if self._camera is None:
            return []
        try:
            config = self._camera.get_config()
            result = []
            for name in self._SETTINGS_NAMES:
                try:
                    widget = config.get_child_by_name(name)
                    wtype = widget.get_type()
                    entry = {
                        "name": name,
                        "label": widget.get_label(),
                        "value": widget.get_value(),
                        "readonly": bool(widget.get_readonly()),
                    }
                    if wtype in (gp.GP_WIDGET_RADIO, gp.GP_WIDGET_MENU):
                        entry["type"] = "menu"
                        entry["choices"] = [
                            widget.get_choice(i)
                            for i in range(widget.count_choices())
                        ]
                    elif wtype == gp.GP_WIDGET_RANGE:
                        lo, hi, step = widget.get_range()
                        entry["type"] = "range"
                        entry["min"] = lo
                        entry["max"] = hi
                        entry["step"] = step
                    else:
                        continue  # skip text/date/section widgets
                    result.append(entry)
                except gp.GPhoto2Error:
                    pass  # not available on this camera
            return result
        except gp.GPhoto2Error as e:
            logger.error("Failed to read camera config: %s", e)
            return []

    def set_camera_setting(self, name: str, value: str) -> bool:
        import gphoto2 as gp
        if self._camera is None:
            return False
        try:
            config = self._camera.get_config()
            widget = config.get_child_by_name(name)
            wtype = widget.get_type()
            if wtype == gp.GP_WIDGET_RANGE:
                widget.set_value(float(value))
            else:
                widget.set_value(value)
            self._camera.set_config(config)
            logger.info("Camera setting %s → %s", name, value)
            return True
        except gp.GPhoto2Error as e:
            logger.error("Failed to set %s=%s: %s", name, value, e)
            return False


def create_camera(mode: str = "mock") -> Camera:
    """Factory function to create the appropriate camera backend."""
    if mode == "gphoto2":
        return GPhotoCamera()
    return MockCamera()
