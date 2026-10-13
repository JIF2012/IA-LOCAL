"""Reconocimiento de texto (OCR) con Tesseract para escaneos e imágenes."""

import io
import logging
import shutil

from PIL import Image, ImageSequence

from .. import config
from .base import ExtractionError, Fragment

log = logging.getLogger(__name__)


def available() -> bool:
    return config.settings.ocr_enabled and shutil.which("tesseract") is not None


def image_to_text(image: Image.Image) -> str:
    import pytesseract

    try:
        return pytesseract.image_to_string(
            image,
            lang=config.settings.ocr_languages,
            timeout=config.settings.ocr_timeout_s,
        ).strip()
    except RuntimeError as exc:  # pytesseract lanza RuntimeError al vencer el timeout
        log.warning("OCR cancelado: %s", exc)
        return ""


def fit_image(image: Image.Image) -> Image.Image:
    """Reduce imágenes enormes para que Tesseract no se quede sin memoria."""
    max_side = config.settings.ocr_max_side_px
    if max(image.size) <= max_side:
        return image
    scale = max_side / max(image.size)
    return image.resize((int(image.width * scale), int(image.height * scale)))


def extract_image(data: bytes) -> list[Fragment]:
    if not available():
        raise ExtractionError("El OCR está desactivado o Tesseract no está instalado.")
    try:
        image = Image.open(io.BytesIO(data))
    except Exception as exc:
        raise ExtractionError(f"No se pudo abrir la imagen: {exc}") from exc

    fragments = []
    # Los TIFF de escáner pueden traer varias páginas.
    for index, frame in enumerate(ImageSequence.Iterator(image)):
        if index >= config.settings.ocr_max_pages:
            break
        text = image_to_text(fit_image(frame.convert("L")))
        if text:
            fragments.append(
                Fragment(text, {"page": index, "page_label": str(index + 1), "metodo": "ocr"})
            )
    return fragments
