import shutil
import subprocess

import pytest

from conversor.extractores import extract


def _joined(fragments) -> str:
    return "\n\n".join(f.text for f in fragments)


def check_plan_text(text: str) -> None:
    assert "Unidades del dibujo: m" in text
    assert "DORMITORIO 1 (x2)" in text
    assert "HORMIGÓN H-30" in text
    assert "AMPLIACIÓN ÑUÑOA" in text
    # cajetín en la presentación, con sus atributos
    assert "PROYECTO: Edificio Los Álamos; LAMINA: ARQ-01" in text
    assert "CONSTRUCTORA DE PRUEBA" in text
    # tabla: celdas en orden de lectura (fila por fila)
    assert "- CUADRO DE SUPERFICIES\n- Primer piso\n- 85,4 m²" in text
    # conteo de bloques y cotas
    assert "| PUERTA_90 | 3 | PUERTAS |" in text
    assert "- 10" in text
    # rectángulo cerrado 10 x 5 (perímetro 30) + línea de 4
    assert "| MUROS | 2 | 34 | 50 (1 polilínea) |" in text


def test_dxf(plan_dxf_bytes):
    kind, fragments = extract(plan_dxf_bytes, "casa.dxf")
    assert kind == "dxf"
    text = _joined(fragments)
    check_plan_text(text)
    assert all(f.metadata["seccion"] for f in fragments)


def test_dxf_detected_without_extension(plan_dxf_bytes):
    kind, _ = extract(plan_dxf_bytes, "sin_extension")
    assert kind == "dxf"


@pytest.mark.skipif(not shutil.which("dxf2dwg") or not shutil.which("dwg2dxf"), reason="requiere LibreDWG")
def test_dwg_roundtrip(plan_r2000_path, tmp_path):
    # LibreDWG escribe un DWG a partir del DXF; luego el conversor lo lee como cualquier DWG.
    target = tmp_path / "casa.dwg"
    subprocess.run(
        ["dxf2dwg", "-y", "-o", str(target), str(plan_r2000_path)], capture_output=True, timeout=120
    )
    assert target.exists(), "dxf2dwg no generó el DWG"

    kind, fragments = extract(target.read_bytes(), "casa.dwg")
    assert kind == "dwg"
    text = _joined(fragments)
    assert "Versión: AC1015" in text
    check_plan_text(text)


def test_dwg_invalid_file():
    from conversor.extractores import ExtractionError

    if not shutil.which("dwg2dxf"):
        pytest.skip("requiere LibreDWG")
    with pytest.raises(ExtractionError):
        extract(b"AC1032" + b"\x00" * 200, "roto.dwg")
