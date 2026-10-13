"""Uso por línea de comandos, útil para revisar qué "ve" la IA de un archivo:

    convertir plano.dwg contrato.docx            # muestra el texto
    convertir --salida /datos/textos *.dwg      # guarda un .md por archivo
"""

import argparse
import sys
from pathlib import Path

from .extractores import ExtractionError, UnsupportedFormat, extract


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="convertir", description="Convierte documentos a texto para la IA.")
    parser.add_argument("archivos", nargs="+", type=Path)
    parser.add_argument("--salida", type=Path, help="carpeta donde guardar un .md por archivo")
    args = parser.parse_args(argv)

    errors = 0
    for path in args.archivos:
        try:
            kind, fragments = extract(path.read_bytes(), path.name)
        except (OSError, ExtractionError, UnsupportedFormat) as exc:
            print(f"ERROR {path}: {exc}", file=sys.stderr)
            errors += 1
            continue
        text = "\n\n".join(f.text for f in fragments)
        if args.salida:
            args.salida.mkdir(parents=True, exist_ok=True)
            target = args.salida / f"{path.name}.md"
            target.write_text(text + "\n", encoding="utf-8")
            print(f"{path} ({kind}) -> {target}", file=sys.stderr)
        else:
            print(text)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
