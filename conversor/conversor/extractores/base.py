from dataclasses import dataclass, field


@dataclass
class Fragment:
    """Un trozo de texto extraído (una página, una hoja, una sección del plano...)."""

    text: str
    metadata: dict = field(default_factory=dict)


class ExtractionError(Exception):
    """El archivo es del tipo correcto pero no se pudo leer (mensaje en español)."""


class UnsupportedFormat(Exception):
    """El tipo de archivo no está soportado."""


def md_cell(value) -> str:
    """Texto apto para una celda de tabla Markdown."""
    if value is None:
        return ""
    text = str(value).replace("\r", " ").replace("\n", " ").replace("|", "\\|")
    return " ".join(text.split())


def md_table(rows: list[list[str]]) -> str:
    """Tabla Markdown; la primera fila se usa como encabezado."""
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [list(r) + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(lines)


def format_number(value: float, decimals: int = 6) -> str:
    if value == int(value) and abs(value) < 1e15:
        return str(int(value))
    return f"{value:.{decimals}f}".rstrip("0").rstrip(".")
