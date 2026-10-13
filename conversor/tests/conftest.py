import io

import ezdxf
import pytest


def build_plan(version: str = "R2018") -> ezdxf.document.Drawing:
    """Plano de prueba: textos con tildes, cajetín con atributos, puertas, cotas y un recinto."""
    doc = ezdxf.new(version, setup=True)
    doc.header["$INSUNITS"] = 6  # metros
    for name in ("MUROS", "TEXTOS", "COTAS", "PUERTAS"):
        doc.layers.add(name)

    door = doc.blocks.new("PUERTA_90")
    door.add_line((0, 0), (0.9, 0))
    door.add_text("P1", dxfattribs={"height": 0.1}).set_placement((0.3, 0.1))

    title = doc.blocks.new("CAJETIN")
    title.add_text("CONSTRUCTORA DE PRUEBA").set_placement((0, 3))
    title.add_attdef("PROYECTO", (0, 2))
    title.add_attdef("LAMINA", (0, 1))

    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (10, 0), (10, 5), (0, 5)], close=True, dxfattribs={"layer": "MUROS"})
    msp.add_line((0, 7), (4, 7), dxfattribs={"layer": "MUROS"})
    msp.add_text("DORMITORIO 1", dxfattribs={"layer": "TEXTOS"}).set_placement((2, 2))
    msp.add_text("DORMITORIO 1", dxfattribs={"layer": "TEXTOS"}).set_placement((7, 2))
    msp.add_mtext("NOTAS:\\PHORMIGÓN H-30\\PACERO A630-420H", dxfattribs={"layer": "TEXTOS"}).set_location((0, 10))
    msp.add_text("AMPLIACIÓN ÑUÑOA", dxfattribs={"layer": "TEXTOS"}).set_placement((0, 12))
    for x in (1, 4, 6):
        msp.add_blockref("PUERTA_90", (x, 0), dxfattribs={"layer": "PUERTAS"})
    dim = msp.add_linear_dim(base=(0, -1), p1=(0, 0), p2=(10, 0), dxfattribs={"layer": "COTAS"})
    dim.render()

    # Las tablas de AutoCAD (ACAD_TABLE) guardan sus celdas en un bloque anónimo *T.
    table = doc.blocks.new_anonymous_block(type_char="T")
    table.add_mtext("CUADRO DE SUPERFICIES").set_location((0, 2))
    table.add_mtext("Primer piso").set_location((0, 1))
    table.add_mtext("85,4 m²").set_location((5, 1))

    psp = doc.paperspace("Layout1")
    ref = psp.add_blockref("CAJETIN", (0, 0))
    ref.add_auto_attribs({"PROYECTO": "Edificio Los Álamos", "LAMINA": "ARQ-01"})
    return doc


@pytest.fixture
def plan_dxf_bytes() -> bytes:
    stream = io.StringIO()
    build_plan().write(stream)
    return stream.getvalue().encode("utf-8")


@pytest.fixture
def plan_r2000_path(tmp_path):
    """DXF R2000 (textos en cp1252, igual que un DWG de AutoCAD 2000-2006)."""
    path = tmp_path / "casa_r2000.dxf"
    build_plan("R2000").saveas(path)
    return path
