# Conversor de documentos para la IA local: PDF (con OCR), Word, Excel,
# PowerPoint, imágenes y planos AutoCAD DWG/DXF.

# --- Etapa 1: compilar LibreDWG (lector libre de DWG; no viene empaquetado en Ubuntu/Debian)
FROM ubuntu:24.04 AS libredwg

RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential pkg-config python3 xz-utils \
 && rm -rf /var/lib/apt/lists/*
# Si cambias la versión, actualiza también el sha256.
ADD --checksum=sha256:62ebb73b984f865960f20ed26619ea5f8789d5e3fd088fa40a2598384da81275 \
    https://github.com/LibreDWG/libredwg/releases/download/0.14/libredwg-0.14.tar.xz /tmp/libredwg.tar.xz
RUN mkdir /tmp/libredwg \
 && tar -xJf /tmp/libredwg.tar.xz -C /tmp/libredwg --strip-components=1 \
 && cd /tmp/libredwg \
 && ./configure --prefix=/opt/libredwg --disable-bindings --disable-docs --disable-static \
 && make -j"$(nproc)" \
 && make install-strip \
 && rm -rf /opt/libredwg/share /opt/libredwg/include /tmp/libredwg /tmp/libredwg.tar.xz

# --- Etapa 2: imagen final
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 python3-venv ca-certificates tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng antiword \
 && rm -rf /var/lib/apt/lists/*

COPY --from=libredwg /opt/libredwg /opt/libredwg
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:/opt/libredwg/bin:${PATH}" \
    LD_LIBRARY_PATH="/opt/libredwg/lib" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    XDG_CACHE_HOME=/tmp/.cache

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY conversor ./conversor
RUN printf '#!/bin/sh\nexec python -m conversor "$@"\n' > /usr/local/bin/convertir \
 && chmod +x /usr/local/bin/convertir \
 && useradd --system --home-dir /app conversor

USER conversor
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
CMD ["uvicorn", "conversor.app:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "warning"]
