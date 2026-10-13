"""Configuración leída desde variables de entorno (ver docker-compose.yml)."""

import os
from dataclasses import dataclass


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "si", "sí", "yes", "on")


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


@dataclass(frozen=True)
class Settings:
    # Clave compartida con Open WebUI (EXTERNAL_DOCUMENT_LOADER_API_KEY).
    # Vacía = sin autenticación (solo recomendable dentro de la red de Docker).
    api_key: str = os.getenv("CONVERSOR_API_KEY", "")
    # Cuántos documentos se procesan a la vez (el OCR y los DWG usan mucha CPU).
    concurrency: int = _int("CONVERSOR_CONCURRENCIA", 2)

    ocr_enabled: bool = _bool("OCR_ACTIVADO", True)
    ocr_languages: str = os.getenv("OCR_IDIOMAS", "spa+eng")
    ocr_dpi: int = _int("OCR_DPI", 300)
    # Lado máximo de la imagen enviada al OCR: evita imágenes gigantes con planos A0.
    ocr_max_side_px: int = _int("OCR_MAX_LADO_PX", 7000)
    ocr_max_pages: int = _int("OCR_MAX_PAGINAS", 100)
    ocr_timeout_s: int = _int("OCR_TIMEOUT_SEG", 180)
    # Una página de PDF con menos letras/números que esto se considera escaneada.
    ocr_min_chars: int = _int("OCR_MIN_CARACTERES", 25)

    dwg_timeout_s: int = _int("DWG_TIMEOUT_SEG", 300)
    dwg_max_texts: int = _int("DWG_MAX_TEXTOS", 5000)

    sheet_max_rows: int = _int("HOJA_MAX_FILAS", 5000)


settings = Settings()
