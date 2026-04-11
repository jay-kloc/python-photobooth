"""Event banner — on-screen overlay and photo stamping with caching."""

import logging
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from src.config import settings

logger = logging.getLogger(__name__)

# Cache for pre-rendered overlays (avoids re-rendering every frame)
_overlay_cache = {
    "key": None,       # tuple of settings that affect the overlay
    "size": None,      # (width, height)
    "rgba": None,      # pre-rendered RGBA numpy array
}


def _parse_hex_color(hex_color: str) -> tuple:
    """Parse hex color string like '#ffffffaa' into (R, G, B, A)."""
    h = hex_color.lstrip("#")
    if len(h) == 6:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (r, g, b, 255)
    elif len(h) == 8:
        r, g, b, a = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16)
        return (r, g, b, a)
    return (255, 255, 255, 255)


def _load_logo() -> Image.Image | None:
    logo_path = settings.event_logo
    if not logo_path:
        return None
    path = Path(logo_path)
    if not path.exists():
        return None
    try:
        return Image.open(path).convert("RGBA")
    except Exception as e:
        logger.error("Failed to load logo: %s", e)
        return None


def has_banner() -> bool:
    return bool(settings.event_name or settings.event_date or settings.event_logo)


def has_frame_overlay() -> bool:
    return bool(settings.frame_overlay)


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for fp in font_paths:
        if Path(fp).exists():
            return ImageFont.truetype(fp, size)
    return ImageFont.load_default()


def _cache_key(w: int, h: int) -> tuple:
    """Build a cache key from all settings that affect the overlay appearance."""
    return (
        w, h,
        settings.event_name, settings.event_date, settings.event_logo,
        settings.banner_position, settings.banner_font_size,
        settings.banner_color, settings.banner_bg_color,
        settings.frame_overlay,
    )


def _build_overlay_rgba(w: int, h: int, font_size: int) -> np.ndarray:
    """Pre-render the full overlay (banner + frame) as an RGBA numpy array."""
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))

    # Render banner text/logo
    if has_banner():
        _render_banner_onto(overlay, w, h, font_size)

    # Render frame overlay
    if has_frame_overlay():
        frame_path = settings.frame_overlay
        if frame_path:
            path = Path(frame_path)
            if path.exists():
                try:
                    frame_img = Image.open(path).convert("RGBA")
                    frame_img = frame_img.resize((w, h), Image.Resampling.LANCZOS)
                    overlay = Image.alpha_composite(overlay, frame_img)
                except Exception as e:
                    logger.error("Failed to load frame overlay: %s", e)

    return np.array(overlay)


def _render_banner_onto(overlay: Image.Image, w: int, h: int, font_size: int):
    """Render banner text and logo onto an existing RGBA PIL Image."""
    text_color = _parse_hex_color(settings.banner_color)
    bg_color = _parse_hex_color(settings.banner_bg_color)

    draw = ImageDraw.Draw(overlay)
    font = _get_font(font_size)

    lines = []
    if settings.event_name:
        lines.append(settings.event_name)
    if settings.event_date:
        lines.append(settings.event_date)

    line_height = font_size + 8
    text_block_height = len(lines) * line_height if lines else 0

    logo = _load_logo()
    logo_w, logo_h = 0, 0
    if logo:
        target_logo_h = max(text_block_height, font_size * 2)
        scale = target_logo_h / logo.height
        logo_w = int(logo.width * scale)
        logo_h = target_logo_h
        logo = logo.resize((logo_w, logo_h), Image.Resampling.LANCZOS)

    padding = font_size // 2
    content_height = max(text_block_height, logo_h)
    banner_h = content_height + padding * 2

    if settings.banner_position == "top":
        banner_y = 0
    else:
        banner_y = h - banner_h

    draw.rectangle([(0, banner_y), (w, banner_y + banner_h)], fill=bg_color)

    total_content_w = logo_w + (20 if logo_w and lines else 0)
    if lines:
        max_text_w = max(draw.textlength(line, font=font) for line in lines)
        total_content_w += int(max_text_w)
    else:
        max_text_w = 0

    content_x = (w - total_content_w) // 2

    if logo:
        logo_x = content_x
        logo_y = banner_y + (banner_h - logo_h) // 2
        overlay.paste(logo, (logo_x, logo_y), logo)
        text_x_start = logo_x + logo_w + 20
    else:
        text_x_start = content_x

    text_y = banner_y + (banner_h - text_block_height) // 2
    for line in lines:
        line_w = draw.textlength(line, font=font)
        line_x = text_x_start + (max_text_w - line_w) // 2
        draw.text((line_x + 2, text_y + 2), line, font=font, fill=(0, 0, 0, 160))
        draw.text((line_x, text_y), line, font=font, fill=text_color)
        text_y += line_height


def _get_cached_overlay(w: int, h: int) -> np.ndarray | None:
    """Get the cached RGBA overlay, rebuilding if settings changed."""
    key = _cache_key(w, h)
    if _overlay_cache["key"] == key and _overlay_cache["rgba"] is not None:
        return _overlay_cache["rgba"]

    font_size = max(16, int(w * settings.banner_font_size / 1920))
    rgba = _build_overlay_rgba(w, h, font_size)

    _overlay_cache["key"] = key
    _overlay_cache["size"] = (w, h)
    _overlay_cache["rgba"] = rgba
    logger.info("Overlay cache rebuilt for %dx%d", w, h)
    return rgba


def _fast_composite(frame_bgr: np.ndarray, overlay_rgba: np.ndarray) -> np.ndarray:
    """Fast alpha compositing using OpenCV (no PIL conversion per frame)."""
    alpha = overlay_rgba[:, :, 3:4].astype(np.float32) / 255.0
    overlay_bgr = overlay_rgba[:, :, :3]
    # Convert RGB overlay to BGR
    overlay_bgr = overlay_bgr[:, :, ::-1]

    result = frame_bgr.astype(np.float32)
    overlay_f = overlay_bgr.astype(np.float32)
    result = result * (1.0 - alpha) + overlay_f * alpha
    return result.astype(np.uint8)


def render_banner_on_frame(frame: np.ndarray) -> np.ndarray:
    """Render overlays onto a camera frame (for live preview). Uses cache."""
    h, w = frame.shape[:2]
    overlay_rgba = _get_cached_overlay(w, h)
    if overlay_rgba is None:
        return frame

    # Check if overlay has any non-transparent pixels
    if overlay_rgba[:, :, 3].max() == 0:
        return frame

    return _fast_composite(frame, overlay_rgba)


def stamp_banner_on_photo(photo_path: Path) -> Path:
    """Stamp overlays onto a saved photo file (no cache — full quality)."""
    needs_banner = has_banner() and settings.stamp_on_photo
    needs_frame = has_frame_overlay() and settings.stamp_on_photo

    if not needs_banner and not needs_frame:
        return photo_path

    try:
        img = cv2.imread(str(photo_path))
        if img is None:
            return photo_path

        h, w = img.shape[:2]
        font_size = max(24, int(w * settings.banner_font_size / 1920))
        overlay_rgba = _build_overlay_rgba(w, h, font_size)

        if overlay_rgba[:, :, 3].max() > 0:
            img = _fast_composite(img, overlay_rgba)

        cv2.imwrite(str(photo_path), img)
        logger.info("Overlays stamped on %s", photo_path.name)
    except Exception as e:
        logger.error("Failed to stamp overlays: %s", e)

    return photo_path


def clear_cache():
    """Clear the overlay cache (call after settings change)."""
    _overlay_cache["key"] = None
    _overlay_cache["rgba"] = None
