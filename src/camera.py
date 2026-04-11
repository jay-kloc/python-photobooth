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
        self._camera.init()
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


def create_camera(mode: str = "mock") -> Camera:
    """Factory function to create the appropriate camera backend."""
    if mode == "gphoto2":
        return GPhotoCamera()
    return MockCamera()
