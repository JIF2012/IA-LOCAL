"""API HTTP compatible con el "cargador de documentos externo" de Open WebUI.

Open WebUI (CONTENT_EXTRACTION_ENGINE=external) envía cada archivo subido con
`PUT /process`: el cuerpo es el archivo, `X-Filename` su nombre y
`Authorization: Bearer <clave>`. Se responde una lista de
`{"page_content": ..., "metadata": {...}}`.
"""

import logging
import re
import secrets
import shutil
import threading
import time
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from . import __version__, config
from .extractores import ExtractionError, UnsupportedFormat, extract

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("conversor")

app = FastAPI(title="Conversor de documentos para IA local", version=__version__)
_slots = threading.BoundedSemaphore(max(config.settings.concurrency, 1))

# Open WebUI guarda los archivos como "<uuid>_<nombre original>".
_STORAGE_PREFIX = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}_", re.I)


def original_filename(header: str | None) -> str:
    name = unquote(header or "").replace("\\", "/").rsplit("/", 1)[-1]
    return _STORAGE_PREFIX.sub("", name) or "documento"


def _check_key(request: Request) -> None:
    expected = config.settings.api_key
    if not expected:
        return
    supplied = request.headers.get("authorization", "")
    if not secrets.compare_digest(supplied.encode(), f"Bearer {expected}".encode()):
        raise HTTPException(status_code=401, detail="Clave del conversor incorrecta.")


def _run(data: bytes, filename: str, content_type: str | None):
    with _slots:
        return extract(data, filename, content_type)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": __version__,
        "dwg2dxf": shutil.which("dwg2dxf") is not None,
        "tesseract": shutil.which("tesseract") is not None and config.settings.ocr_enabled,
        "antiword": shutil.which("antiword") is not None,
    }


@app.put("/process")
async def process(request: Request):
    _check_key(request)
    filename = original_filename(request.headers.get("x-filename"))
    content_type = request.headers.get("content-type")
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="El archivo llegó vacío.")

    started = time.monotonic()
    try:
        kind, fragments = await run_in_threadpool(_run, data, filename, content_type)
    except UnsupportedFormat as exc:
        raise HTTPException(status_code=415, detail=f"{filename}: {exc}") from exc
    except ExtractionError as exc:
        log.warning("%s: %s", filename, exc)
        raise HTTPException(status_code=422, detail=f"{filename}: {exc}") from exc
    except Exception as exc:
        log.exception("Error inesperado procesando %s", filename)
        raise HTTPException(status_code=500, detail=f"{filename}: error inesperado ({exc})") from exc

    if not fragments:
        raise HTTPException(status_code=422, detail=f"{filename}: no se encontró texto en el archivo.")

    chars = sum(len(f.text) for f in fragments)
    log.info(
        "%s (%s, %d bytes): %d fragmentos, %d caracteres en %.1f s",
        filename, kind, len(data), len(fragments), chars, time.monotonic() - started,
    )
    return [
        {"page_content": f.text, "metadata": {**f.metadata, "tipo": kind, "conversor": __version__}}
        for f in fragments
    ]
