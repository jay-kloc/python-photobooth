"""Photobooth configuration — runtime-editable settings."""

import json
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
PHOTOS_DIR = PROJECT_ROOT / "photos"
ASSETS_DIR = PROJECT_ROOT / "assets"
SETTINGS_FILE = PROJECT_ROOT / "settings.json"

# Ensure output directory exists
PHOTOS_DIR.mkdir(exist_ok=True)

# Static settings (not editable at runtime)
FULLSCREEN = os.environ.get("PHOTOBOOTH_FULLSCREEN", "1") == "1"
WINDOW_WIDTH = 1280
WINDOW_HEIGHT = 960

# Default values for dynamic settings
_DEFAULTS = {
    "camera_mode": os.environ.get("PHOTOBOOTH_CAMERA", "mock"),
    "countdown_seconds": 3,
    "preview_display_seconds": 5,
    "photo_prefix": "photobooth",
    "event_name": "",
    "event_date": "",
    "event_logo": "",
    "banner_position": "bottom",
    "banner_font_size": 36,
    "banner_color": "#ffffff",
    "banner_bg_color": "#000000aa",
    "stamp_on_photo": True,
    "frame_overlay": "",  # path to PNG frame with transparent center
}


class Settings:
    """Runtime-editable settings backed by a JSON file."""

    def __init__(self):
        self._data = dict(_DEFAULTS)
        self._load_env_overrides()
        self._load_from_file()

    def _load_env_overrides(self):
        """Apply environment variable overrides."""
        env_map = {
            "PHOTOBOOTH_EVENT_NAME": "event_name",
            "PHOTOBOOTH_EVENT_DATE": "event_date",
            "PHOTOBOOTH_EVENT_LOGO": "event_logo",
            "PHOTOBOOTH_BANNER_POS": "banner_position",
            "PHOTOBOOTH_BANNER_FONT_SIZE": ("banner_font_size", int),
            "PHOTOBOOTH_BANNER_COLOR": "banner_color",
            "PHOTOBOOTH_BANNER_BG": "banner_bg_color",
            "PHOTOBOOTH_STAMP": ("stamp_on_photo", lambda v: v == "1"),
        }
        for env_key, mapping in env_map.items():
            val = os.environ.get(env_key)
            if val is not None:
                if isinstance(mapping, tuple):
                    key, converter = mapping
                    self._data[key] = converter(val)
                else:
                    self._data[mapping] = val

    def _load_from_file(self):
        """Load settings from JSON file if it exists."""
        if SETTINGS_FILE.exists():
            try:
                with open(SETTINGS_FILE) as f:
                    saved = json.load(f)
                self._data.update(saved)
                logger.info("Settings loaded from %s", SETTINGS_FILE)
            except Exception as e:
                logger.warning("Failed to load settings: %s", e)

    def save(self):
        """Persist current settings to JSON file."""
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(self._data, f, indent=2)
            logger.info("Settings saved to %s", SETTINGS_FILE)
        except Exception as e:
            logger.error("Failed to save settings: %s", e)

    def get(self, key: str):
        return self._data.get(key, _DEFAULTS.get(key))

    def set(self, key: str, value):
        self._data[key] = value

    # Convenience properties
    @property
    def camera_mode(self): return self.get("camera_mode")
    @property
    def countdown_seconds(self): return self.get("countdown_seconds")
    @property
    def preview_display_seconds(self): return self.get("preview_display_seconds")
    @property
    def photo_prefix(self): return self.get("photo_prefix")
    @property
    def event_name(self): return self.get("event_name")
    @property
    def event_date(self): return self.get("event_date")
    @property
    def event_logo(self): return self.get("event_logo")
    @property
    def banner_position(self): return self.get("banner_position")
    @property
    def banner_font_size(self): return self.get("banner_font_size")
    @property
    def banner_color(self): return self.get("banner_color")
    @property
    def banner_bg_color(self): return self.get("banner_bg_color")
    @property
    def stamp_on_photo(self): return self.get("stamp_on_photo")
    @property
    def frame_overlay(self): return self.get("frame_overlay")


# Global settings instance
settings = Settings()
