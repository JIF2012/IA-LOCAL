"""Detecta el tipo de archivo y llama al extractor correspondiente."""

import io
import zipfile
from pathlib import PurePath

from .base import ExtractionError, Fragment, UnsupportedFormat

EXTENSIONS = {
    "pdf": "pdf",
    "docx": "docx", "docm": "docx", "dotx": "docx",
    "doc": "doc", "dot": "doc",
    "xlsx": "xlsx", "xlsm": "xlsx", "xltx": "xlsx",
    "xls": "xls",
    "pptx": "pptx", "pptm": "pptx",
    "dwg": "dwg",
    "dxf": "dxf",
    "png": "image", "jpg": "image", "jpeg": "image", "tif": "image", "tiff": "image",
    "bmp": "image", "webp": "image", "gif": "image",
}

CONTENT_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.ms-excel": "xls",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",
    "image/vnd.dwg": "dwg", "image/x-dwg": "dwg", "application/acad": "dwg",
    "application/x-acad": "dwg", "application/dwg": "dwg", "application/x-dwg": "dwg",
    "image/vnd.dxf": "dxf", "image/x-dxf": "dxf", "application/dxf": "dxf",
}

OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _sniff(data: bytes) -> str | None:
    """Reconoce el formato por su contenido cuando el nombre no ayuda."""
    head = data[:16]
    if head.startswith(b"%PDF"):
        return "pdf"
    if head[:2] == b"AC" and head[2:6].replace(b".", b"0").isdigit():
        return "dwg"
    if head.startswith(b"AutoCAD Binary DXF"):
        return "dxf"
    if head.startswith(b"PK\x03\x04"):
        try:
            names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        except zipfile.BadZipFile:
            return None
        for prefix, kind in (("word/", "docx"), ("xl/", "xlsx"), ("ppt/", "pptx")):
            if any(n.startswith(prefix) for n in names):
                return kind
        return None
    if head.startswith(OLE_MAGIC):
        if "WordDocument".encode("utf-16-le") in data:
            return "doc"
        if "Workbook".encode("utf-16-le") in data or "Book".encode("utf-16-le") in data:
            return "xls"
        return None
    if head.startswith((b"\x89PNG", b"\xff\xd8\xff", b"II*\x00", b"MM\x00*", b"GIF8", b"BM")):
        return "image"
    if head.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image"
    start = data[:64].lstrip()
    if start.startswith((b"0\r\nSECTION", b"0\nSECTION", b"999")) and b"ENTITIES" in data[:2_000_000]:
        return "dxf"
    return None


def detect_kind(filename: str, content_type: str | None, data: bytes) -> str:
    extension = PurePath(filename or "").suffix.lower().lstrip(".")
    if extension in EXTENSIONS:
        return EXTENSIONS[extension]
    mime = (content_type or "").split(";")[0].strip().lower()
    if mime in CONTENT_TYPES:
        return CONTENT_TYPES[mime]
    return _sniff(data) or "text"


def decode_text(data: bytes) -> str:
    if b"\x00" in data[:8192]:
        raise UnsupportedFormat("El archivo es binario y su formato no está soportado.")
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _extract(kind: str, data: bytes, name: str) -> list[Fragment]:
    if kind == "pdf":
        from . import pdf

        return pdf.extract(data)
    if kind in ("docx", "doc", "xlsx", "xls", "pptx"):
        from . import office

        return getattr(office, f"extract_{kind}")(data)
    if kind in ("dwg", "dxf"):
        from . import cad

        return getattr(cad, f"extract_{kind}")(data, name)
    if kind == "image":
        from . import ocr

        return ocr.extract_image(data)

    text = decode_text(data).strip()
    return [Fragment(text)] if text else []


def extract(data: bytes, filename: str, content_type: str | None = None) -> tuple[str, list[Fragment]]:
    """Devuelve (tipo detectado, fragmentos de texto)."""
    kind = detect_kind(filename, content_type, data)
    fragments = _extract(kind, data, PurePath(filename or "documento").name)
    for fragment in fragments:
        # Archivos con bytes inválidos (p. ej. DWG con textos mal codificados) dejan
        # caracteres que no se pueden enviar como JSON: se reemplazan por "?".
        fragment.text = fragment.text.encode("utf-8", "replace").decode("utf-8")
    return kind, fragments


__all__ = ["ExtractionError", "Fragment", "UnsupportedFormat", "detect_kind", "extract"]
