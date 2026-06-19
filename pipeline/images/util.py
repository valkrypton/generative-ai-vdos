"""Shared image helpers."""
import io

from PIL import Image

WIDTH, HEIGHT = 1920, 1080


def fit_cover(img: Image.Image, width: int = WIDTH, height: int = HEIGHT) -> Image.Image:
    """Resize+crop to exactly width x height, preserving aspect ratio (cover fit)."""
    src_ratio = img.width / img.height
    dst_ratio = width / height
    if src_ratio > dst_ratio:
        new_height = height
        new_width = round(height * src_ratio)
    else:
        new_width = width
        new_height = round(width / src_ratio)
    img = img.resize((new_width, new_height), Image.LANCZOS)
    left = (new_width - width) // 2
    top = (new_height - height) // 2
    return img.crop((left, top, left + width, top + height))


def to_png_bytes(img: Image.Image) -> bytes:
    """Convert a PIL Image to PNG bytes after fit_cover."""
    buf = io.BytesIO()
    fit_cover(img).save(buf, format="PNG")
    return buf.getvalue()
