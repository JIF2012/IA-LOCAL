"""PDF: texto con PyMuPDF y OCR automático para páginas escaneadas."""

import logging

import pymupdf
from PIL import Image

from .. import config
from . import ocr
from .base import ExtractionError, Fragment

log = logging.getLogger(__name__)


def _useful_chars(text: str) -> int:
    return sum(ch.isalnum() for ch in text)


def _looks_scanned(text: str) -> bool:
    if _useful_chars(text) < config.settings.ocr_min_chars:
        return True
    # Fuentes sin tabla Unicode producen "�" en vez de letras: mejor leer la imagen.
    return text.count("�") > 0.3 * len(text)


def _ocr_page(page: pymupdf.Page) -> str:
    zoom = config.settings.ocr_dpi / 72
    longest = max(page.rect.width, page.rect.height) * zoom
    if longest > config.settings.ocr_max_side_px:
        zoom *= config.settings.ocr_max_side_px / longest
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csGRAY)
    image = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    return ocr.image_to_text(image)


def extract(data: bytes) -> list[Fragment]:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise ExtractionError(f"PDF dañado o ilegible: {exc}") from exc

    with doc:
        if doc.needs_pass and not doc.authenticate(""):
            raise ExtractionError("El PDF está protegido con contraseña.")

        can_ocr = ocr.available()
        ocr_pages = 0
        fragments = []
        for index, page in enumerate(doc):
            text = page.get_text("text", sort=True).strip()
            method = "texto"
            if _looks_scanned(text) and can_ocr and ocr_pages < config.settings.ocr_max_pages:
                ocr_pages += 1
                ocr_text = _ocr_page(page)
                if _useful_chars(ocr_text) > _useful_chars(text):
                    text, method = ocr_text, "ocr"
            if text:
                fragments.append(
                    Fragment(
                        text,
                        {
                            "page": index,
                            "page_label": page.get_label() or str(index + 1),
                            "total_pages": doc.page_count,
                            "metodo": method,
                        },
                    )
                )

        if ocr_pages:
            log.info("OCR aplicado a %d de %d páginas", ocr_pages, doc.page_count)
        if not fragments and not can_ocr:
            raise ExtractionError(
                "El PDF no tiene texto (parece escaneado) y el OCR está desactivado."
            )
        return fragments
