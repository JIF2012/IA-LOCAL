"""Planos AutoCAD (.dwg / .dxf) a texto.

El DWG es un formato binario cerrado: primero se convierte a DXF con LibreDWG
(`dwg2dxf`). Luego `ezdxf` recorre el dibujo y se arma un resumen en Markdown con lo que una IA
puede aprovechar: cajetín y atributos de bloques, textos por capa, cotas,
conteo de bloques (puertas, artefactos...) y longitudes/áreas por capa.
"""

import logging
import math
import shutil
import subprocess
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import ezdxf
from ezdxf import recover
from ezdxf.document import Drawing
from ezdxf.tools.text import plain_mtext

from .. import config
from .base import ExtractionError, Fragment, format_number, md_cell, md_table

log = logging.getLogger(__name__)

ACAD_VERSIONS = {
    "AC1009": "AutoCAD R11/R12",
    "AC1012": "AutoCAD R13",
    "AC1014": "AutoCAD R14",
    "AC1015": "AutoCAD 2000-2002",
    "AC1018": "AutoCAD 2004-2006",
    "AC1021": "AutoCAD 2007-2009",
    "AC1024": "AutoCAD 2010-2012",
    "AC1027": "AutoCAD 2013-2017",
    "AC1032": "AutoCAD 2018 o posterior",
}

UNITS = {1: "pulg", 2: "pies", 4: "mm", 5: "cm", 6: "m", 7: "km", 14: "dm"}
# Las longitudes y áreas se informan en metros cuando el dibujo usa unidades métricas.
TO_METERS = {"mm": 0.001, "cm": 0.01, "dm": 0.1, "m": 1.0, "km": 1000.0}

TEXT_TYPES = {"TEXT", "MTEXT", "MULTILEADER", "ATTDEF"}
# Bloques anónimos que no aportan texto propio: cotas (*D), sombreados, grupos.
SKIP_BLOCK_PREFIXES = ("*D", "*X", "*A", "*E")


# ---------------------------------------------------------------- DWG -> DXF


def _tail(text: str, lines: int = 5) -> str:
    return " | ".join(text.strip().splitlines()[-lines:])


def _read_dxf(path: Path) -> Drawing:
    doc, auditor = recover.readfile(str(path))
    if auditor.has_errors:
        log.info("DXF con %d errores corregidos automáticamente", len(auditor.errors))
    return doc


def dwg_to_drawing(data: bytes) -> Drawing:
    if not shutil.which("dwg2dxf"):
        raise ExtractionError("No está instalado dwg2dxf (LibreDWG), necesario para leer DWG.")

    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "plano.dwg"
        out = Path(tmp) / "plano.dxf"
        src.write_bytes(data)
        try:
            proc = subprocess.run(
                ["dwg2dxf", "-y", "-o", str(out), str(src)],
                capture_output=True,
                text=True,
                errors="replace",
                timeout=config.settings.dwg_timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            raise ExtractionError(
                f"La conversión del DWG tardó más de {config.settings.dwg_timeout_s} s."
            ) from exc

        # dwg2dxf a veces termina con código de error pero igual genera un DXF útil.
        if not out.exists() or out.stat().st_size == 0:
            detail = _tail(proc.stderr or proc.stdout) or f"código {proc.returncode}"
            raise ExtractionError(
                f"No se pudo leer el DWG ({detail}). Prueba guardándolo como DXF desde AutoCAD."
            )
        try:
            return _read_dxf(out)
        except Exception as exc:
            raise ExtractionError(
                f"El DWG se convirtió pero el resultado es ilegible ({exc}). "
                "Prueba guardándolo como DXF desde AutoCAD."
            ) from exc


def dxf_to_drawing(data: bytes) -> Drawing:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "plano.dxf"
        path.write_bytes(data)
        try:
            return _read_dxf(path)
        except Exception as exc:
            raise ExtractionError(f"DXF dañado o ilegible: {exc}") from exc


# ---------------------------------------------------------------- geometría


def _bulge_length(p1, p2, bulge: float) -> float:
    chord = math.dist(p1, p2)
    if not bulge or chord == 0:
        return chord
    angle = 4 * math.atan(abs(bulge))
    return chord * angle / (2 * math.sin(angle / 2))


def _polyline_length(points: list[tuple[float, float, float]], closed: bool) -> float:
    """points: (x, y, bulge) en el plano de la polilínea."""
    if closed and len(points) > 1:
        points = points + [points[0]]
    return sum(
        _bulge_length(a[:2], b[:2], a[2]) for a, b in zip(points, points[1:])
    )


def entity_length(entity) -> float:
    kind = entity.dxftype()
    try:
        if kind == "LINE":
            return entity.dxf.start.distance(entity.dxf.end)
        if kind == "LWPOLYLINE":
            return _polyline_length(list(entity.get_points("xyb")), entity.closed)
        if kind == "POLYLINE" and entity.is_2d_polyline:
            points = [
                (v.dxf.location.x, v.dxf.location.y, v.dxf.get("bulge", 0.0))
                for v in entity.vertices
            ]
            return _polyline_length(points, entity.is_closed)
        if kind == "POLYLINE" and entity.is_3d_polyline:  # tramos rectos en 3D
            locations = [v.dxf.location for v in entity.vertices]
            if entity.is_closed and len(locations) > 1:
                locations.append(locations[0])
            return sum(a.distance(b) for a, b in zip(locations, locations[1:]))
        if kind == "ARC":
            span = (entity.dxf.end_angle - entity.dxf.start_angle) % 360 or 360
            return entity.dxf.radius * math.radians(span)
        if kind == "CIRCLE":
            return 2 * math.pi * entity.dxf.radius
        if kind in ("SPLINE", "ELLIPSE"):
            from ezdxf import path

            vertices = list(path.make_path(entity).flattening(0.01))
            return sum(a.distance(b) for a, b in zip(vertices, vertices[1:]))
    except Exception:
        pass
    return 0.0


def closed_area(entity, length: float) -> float:
    """Área de polilíneas cerradas (recintos, losas, terrenos...)."""
    kind = entity.dxftype()
    if kind == "LWPOLYLINE" and entity.closed:
        pass
    elif kind == "POLYLINE" and entity.is_2d_polyline and entity.is_closed:
        pass
    else:
        return 0.0
    try:
        from ezdxf import path
        from ezdxf.math import area

        tolerance = max(length * 1e-4, 1e-9)
        return abs(area(list(path.make_path(entity).flattening(tolerance))))
    except Exception:
        return 0.0


# ---------------------------------------------------------------- recorrido


def clean(text: str) -> str:
    lines = [" ".join(line.split()) for line in text.replace("\r", "\n").split("\n")]
    return "\n".join(line for line in lines if line).strip()


def entity_text(entity) -> str:
    kind = entity.dxftype()
    try:
        if kind in ("TEXT", "ATTDEF"):
            return clean(entity.plain_text())
        if kind == "ATTRIB":
            if entity.has_embedded_mtext_entity:
                return clean(entity.virtual_mtext_entity().plain_text(split=False))
            return clean(entity.plain_text())
        if kind == "MTEXT":
            return clean(entity.plain_text(split=False))
        if kind == "MULTILEADER":
            mtext = entity.context.mtext
            return clean(plain_mtext(mtext.default_content)) if mtext else ""
    except Exception:
        log.debug("No se pudo leer el texto de %s", kind, exc_info=True)
    return ""


def entity_position(entity) -> tuple[float, float]:
    try:
        if entity.dxftype() == "MULTILEADER":
            point = entity.context.mtext.insert
        else:
            point = entity.dxf.insert
        return point.x, point.y
    except Exception:
        return 0.0, 0.0


def dimension_text(entity) -> str:
    override = (entity.dxf.get("text", "") or "").strip()
    if override and override != "<>" and "<>" not in override:
        return clean(plain_mtext(override))
    value = entity.dxf.get("actual_measurement")
    if not value:  # algunos conversores dejan la medida guardada en 0
        try:
            value = entity.get_measurement()
        except Exception:
            value = None
    if not isinstance(value, (int, float)):
        return clean(plain_mtext(override.replace("<>", ""))) if override else ""
    if entity.dimtype in (2, 5):  # angulares: el DXF guarda radianes
        shown = f"{format_number(math.degrees(value), 2)}°"
    else:
        shown = format_number(value, 3)
    return clean(plain_mtext(override.replace("<>", shown))) if override else shown


def effective_block_name(doc: Drawing, name: str) -> str:
    """Nombre real de un bloque dinámico (AutoCAD los guarda como *U123)."""
    if not name.startswith("*U"):
        return name
    try:
        record = doc.blocks.get(name).block_record
        for code, value in record.get_xdata("AcDbBlockRepBTag"):
            if code == 1005:
                original = doc.entitydb.get(value)
                if original is not None:
                    return original.dxf.name
    except Exception:
        pass
    return name


@dataclass
class LayerStats:
    entities: int = 0
    length: float = 0.0
    area: float = 0.0
    closed: int = 0


@dataclass
class Survey:
    # layout -> capa -> texto -> [cantidad, x, y]
    texts: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(dict)))
    # layout -> bloque -> "TAG: valor; ..." -> cantidad
    attributes: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(Counter)))
    # capa -> cota -> cantidad
    dimensions: dict = field(default_factory=lambda: defaultdict(Counter))
    blocks: Counter = field(default_factory=Counter)
    block_layers: dict = field(default_factory=lambda: defaultdict(set))
    used_blocks: set = field(default_factory=set)
    layers: dict = field(default_factory=lambda: defaultdict(LayerStats))
    entity_types: Counter = field(default_factory=Counter)


def _add_text(bucket: dict, text: str, entity) -> None:
    if not text:
        return
    if text in bucket:
        bucket[text][0] += 1
    else:
        bucket[text] = [1, *entity_position(entity)]


def survey_drawing(doc: Drawing) -> Survey:
    survey = Survey()
    names: dict[str, str] = {}
    for layout in doc.layouts:
        layout_name = "Modelo" if layout.is_modelspace else f"Presentación «{layout.name}»"
        for entity in layout:
            kind = entity.dxftype()
            layer = entity.dxf.get("layer", "0")
            survey.entity_types[kind] += 1
            stats = survey.layers[layer]
            stats.entities += 1

            if kind in TEXT_TYPES:
                _add_text(survey.texts[layout_name][layer], entity_text(entity), entity)
            elif kind == "DIMENSION":
                text = dimension_text(entity)
                if text:
                    survey.dimensions[layer][text] += 1
            elif kind == "INSERT":
                raw_name = entity.dxf.name
                if raw_name not in names:
                    names[raw_name] = effective_block_name(doc, raw_name)
                name = names[raw_name]
                survey.used_blocks.add(raw_name)
                if not name.startswith("*"):
                    survey.blocks[name] += 1
                    survey.block_layers[name].add(layer)
                values = []
                for attrib in entity.attribs:
                    value = entity_text(attrib)
                    if value:
                        values.append(f"{attrib.dxf.tag}: {value}".replace("\n", " / "))
                if values:
                    survey.attributes[layout_name][name]["; ".join(values)] += 1
            else:
                length = entity_length(entity)
                if length:
                    stats.length += length
                    area = closed_area(entity, length)
                    if area:
                        stats.area += area
                        stats.closed += 1
    return survey


def _nested_blocks(doc: Drawing, names: set) -> set:
    """Bloques usados directa o indirectamente (bloques dentro de bloques)."""
    pending, seen = list(names), set()
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        block = doc.blocks.get(name)
        if block is None:
            continue
        pending += [e.dxf.name for e in block.query("INSERT")]
    return seen


def block_texts(doc: Drawing, used: set) -> dict:
    """Textos fijos dibujados dentro de los bloques (rótulos, tablas, cajetines)."""
    # Las tablas (ACAD_TABLE) dibujan sus celdas en bloques anónimos *T.
    tables = {b.name for b in doc.blocks if b.name.upper().startswith("*T")}
    result = {}
    for name in sorted(_nested_blocks(doc, used | tables)):
        if name.upper().startswith(SKIP_BLOCK_PREFIXES):
            continue
        block = doc.blocks.get(name)
        if block is None or block.block_record.is_any_layout:
            continue
        texts = {}
        for entity in block:
            if entity.dxftype() in ("TEXT", "MTEXT", "MULTILEADER"):
                _add_text(texts, entity_text(entity), entity)
        if texts:
            label = effective_block_name(doc, name)
            if name.upper().startswith("*T"):
                label = f"Tabla ({name})"
            result.setdefault(label, {}).update(texts)
    return result


# ---------------------------------------------------------------- Markdown


def _sorted_texts(texts: dict) -> list[str]:
    # De arriba hacia abajo y de izquierda a derecha, como se lee una lámina.
    ordered = sorted(texts.items(), key=lambda item: (-round(item[1][2], 1), item[1][1]))
    lines = []
    for text, (count, _x, _y) in ordered:
        text = text.replace("\n", "\n  ")
        lines.append(f"- {text}" + (f" (x{count})" if count > 1 else ""))
    return lines


def _numeric_key(text: str) -> tuple:
    try:
        return (0, float(text.replace(",", ".")), text)
    except ValueError:
        return (1, 0.0, text)


def _header_info(doc: Drawing, filename: str, source_version: str | None) -> list[str]:
    header = doc.header
    lines = [f"- Archivo: {filename}"]
    version = source_version or header.get("$ACADVER", "")
    if version:
        lines.append(f"- Versión: {version} ({ACAD_VERSIONS.get(version, 'desconocida')})")
    units = UNITS.get(header.get("$INSUNITS", 0))
    lines.append(f"- Unidades del dibujo: {units or 'sin unidad definida'}")
    try:
        from ezdxf.tools.juliandate import calendardate

        updated = calendardate(header.get("$TDUPDATE"))
        lines.append(f"- Última modificación guardada en el archivo: {updated:%Y-%m-%d %H:%M}")
    except Exception:
        pass
    try:
        extmin, extmax = header.get("$EXTMIN"), header.get("$EXTMAX")
        width, height = extmax[0] - extmin[0], extmax[1] - extmin[1]
        if 0 < width < 1e12 and 0 < height < 1e12:
            unit = f" {units}" if units else ""
            lines.append(
                f"- Tamaño total del dibujo: {format_number(width, 2)} x {format_number(height, 2)}{unit}"
            )
    except Exception:
        pass
    layouts = [name for name in doc.layouts.names_in_taborder() if name.lower() != "model"]
    if layouts:
        lines.append(f"- Presentaciones (láminas): {', '.join(layouts)}")
    return lines


def drawing_to_fragments(doc: Drawing, filename: str, source_version: str | None = None) -> list[Fragment]:
    survey = survey_drawing(doc)
    units = UNITS.get(doc.header.get("$INSUNITS", 0))
    unit_label = units or "unidades"
    factor = TO_METERS.get(units, 1.0)
    size_label = "m" if units in TO_METERS else unit_label
    budget = config.settings.dwg_max_texts
    truncated = False

    def take(lines: list[str]) -> list[str]:
        nonlocal budget, truncated
        if len(lines) > budget:
            truncated = True
        kept = lines[: max(budget, 0)]
        budget -= len(kept)
        return kept

    fragments: list[Fragment] = []

    def add(section: str, body: list[str]) -> None:
        if body:
            text = f"# Plano {filename} — {section}\n\n" + "\n".join(body).strip()
            fragments.append(Fragment(text, {"seccion": section}))

    summary = _header_info(doc, filename, source_version)
    summary += [
        f"- Capas con elementos: {sum(1 for s in survey.layers.values() if s.entities)}",
        f"- Elementos dibujados: {sum(survey.entity_types.values())}",
        "",
        "Este texto fue extraído automáticamente del plano. Incluye textos, atributos de "
        "bloques, cotas, conteo de bloques y totales de longitud/área por capa; no incluye "
        "el dibujo en sí, así que la ubicación exacta de cada elemento no está disponible.",
    ]
    xrefs = [b.name for b in doc.blocks if b.block_record.is_xref]
    if xrefs:
        summary.append(
            "Referencias externas (XREF) no incluidas: " + ", ".join(sorted(xrefs))
        )
    add("Resumen", summary)

    for layout_name, blocks in survey.attributes.items():
        body = []
        for block_name in sorted(blocks):
            entries = blocks[block_name]
            body.append(f"\n### Bloque {block_name}")
            lines = [
                f"- {values}" + (f" (x{count})" if count > 1 else "")
                for values, count in sorted(entries.items(), key=lambda kv: -kv[1])
            ]
            body += take(lines)
        add(f"Atributos de bloques (cajetín, rótulos) — {layout_name}", body)

    for layout_name, layers in survey.texts.items():
        body = []
        for layer in sorted(layers):
            body.append(f"\n### Capa {layer}")
            body += take(_sorted_texts(layers[layer]))
        add(f"Textos — {layout_name}", body)

    inner = block_texts(doc, survey.used_blocks)
    if inner:
        body = []
        for block_name, texts in inner.items():
            uses = survey.blocks.get(block_name)
            if uses:
                block_name += f" (insertado {uses} {'vez' if uses == 1 else 'veces'})"
            body.append(f"\n### {block_name}")
            body += take(_sorted_texts(texts))
        add("Textos dentro de bloques", body)

    if survey.dimensions:
        body = [f"Medidas en {unit_label}. (xN) = cantidad de cotas con ese valor."]
        for layer in sorted(survey.dimensions):
            body.append(f"\n### Capa {layer}")
            values = sorted(survey.dimensions[layer].items(), key=lambda kv: _numeric_key(kv[0]))
            body += take([f"- {v}" + (f" (x{c})" if c > 1 else "") for v, c in values])
        add("Cotas", body)

    if survey.blocks:
        rows = [["Bloque", "Cantidad", "Capas"]]
        for name, count in survey.blocks.most_common():
            rows.append([md_cell(name), str(count), md_cell(", ".join(sorted(survey.block_layers[name])))])
        add("Conteo de bloques insertados (puertas, ventanas, artefactos, símbolos...)", [md_table(rows)])

    rows = [["Capa", "Elementos", f"Longitud total ({size_label})", f"Área cerrada ({size_label}²)", "Estado"]]
    for name in sorted(survey.layers, key=str.casefold):
        stats = survey.layers[name]
        if not stats.entities:
            continue
        state = []
        layer = doc.layers.get(name) if doc.layers.has_entry(name) else None
        if layer is not None:
            if layer.is_off():
                state.append("apagada")
            if layer.is_frozen():
                state.append("congelada")
        area = ""
        if stats.closed:
            plural = "polilínea" if stats.closed == 1 else "polilíneas"
            area = f"{format_number(stats.area * factor**2, 2)} ({stats.closed} {plural})"
        rows.append([
            md_cell(name),
            str(stats.entities),
            format_number(stats.length * factor, 2) if stats.length else "",
            area,
            ", ".join(state),
        ])
    add(
        "Capas",
        [
            "Longitud: suma de líneas, polilíneas, arcos y círculos de la capa. "
            "Área: suma de las polilíneas cerradas de la capa.",
            "",
            md_table(rows),
        ],
    )

    if truncated:
        fragments.append(
            Fragment(
                f"# Plano {filename} — Aviso\n\nEl plano tiene demasiados textos; se incluyeron "
                f"solo los primeros {config.settings.dwg_max_texts} (DWG_MAX_TEXTOS).",
                {"seccion": "Aviso"},
            )
        )
    return fragments


def dwg_version(data: bytes) -> str | None:
    head = data[:6].decode("ascii", "replace")
    return head if head.startswith("AC") else None


def extract_dwg(data: bytes, filename: str) -> list[Fragment]:
    doc = dwg_to_drawing(data)
    return drawing_to_fragments(doc, filename, dwg_version(data))


def extract_dxf(data: bytes, filename: str) -> list[Fragment]:
    return drawing_to_fragments(dxf_to_drawing(data), filename)
