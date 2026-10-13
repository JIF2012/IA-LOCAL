import dataclasses

import pymupdf
import pytest
from fastapi.testclient import TestClient

from conversor import app as app_module
from conversor import config


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "settings", dataclasses.replace(config.settings, api_key="secreta"))
    return TestClient(app_module.app)


def _pdf() -> bytes:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Acta de entrega de obra")
    return doc.tobytes()


def test_process_like_open_webui(client, plan_dxf_bytes):
    # Así llama Open WebUI: PUT /process, nombre "<uuid>_<archivo>" codificado en X-Filename.
    response = client.put(
        "/process",
        content=plan_dxf_bytes,
        headers={
            "Authorization": "Bearer secreta",
            "Content-Type": "application/octet-stream",
            "X-Filename": "0f8fad5b-d9cb-469f-a165-70867728950e_Planta%20Casa.dxf",
        },
    )
    assert response.status_code == 200, response.text
    documents = response.json()
    assert all(set(d) == {"page_content", "metadata"} for d in documents)
    assert documents[0]["page_content"].startswith("# Plano Planta Casa.dxf — Resumen")
    assert documents[0]["metadata"]["tipo"] == "dxf"


def test_invalid_bytes_in_drawing_text(client, plan_r2000_path):
    # Un plano con un byte que no existe en su página de códigos (0x81 en cp1252)
    # debe responder igual, sin romper el JSON.
    data = plan_r2000_path.read_bytes().replace(b"DORMITORIO 1", b"DORMITORIO \x81")
    response = client.put(
        "/process",
        content=data,
        headers={"Authorization": "Bearer secreta", "X-Filename": "raro.dxf"},
    )
    assert response.status_code == 200, response.text
    assert "DORMITORIO ?" in "\n".join(d["page_content"] for d in response.json())


def test_process_pdf_pages(client):
    response = client.put(
        "/process",
        content=_pdf(),
        headers={"Authorization": "Bearer secreta", "Content-Type": "application/pdf", "X-Filename": "acta.pdf"},
    )
    assert response.status_code == 200
    assert "Acta de entrega" in response.json()[0]["page_content"]
    assert response.json()[0]["metadata"]["page"] == 0


def test_rejects_wrong_key(client):
    response = client.put("/process", content=b"hola", headers={"Authorization": "Bearer otra"})
    assert response.status_code == 401


def test_unreadable_file_returns_clear_error(client):
    response = client.put(
        "/process",
        content=b"%PDF-1.7 esto no es un pdf",
        headers={"Authorization": "Bearer secreta", "X-Filename": "roto.pdf"},
    )
    assert response.status_code == 422
    assert "roto.pdf" in response.json()["detail"]


def test_binary_unknown_format(client):
    response = client.put(
        "/process",
        content=b"\x00\x01\x02" * 100,
        headers={"Authorization": "Bearer secreta", "X-Filename": "algo.xyz"},
    )
    assert response.status_code == 415


def test_health(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
