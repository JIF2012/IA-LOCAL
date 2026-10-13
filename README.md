# IA Local en ZimaOS

Una IA tipo ChatGPT que corre **dentro de tu servidor Zima**, sin enviar nada a internet, y que
puede leer **PDF, Word, Excel, PowerPoint y planos AutoCAD (DWG/DXF)**.

```
 Navegador (PC, celular)
        │  http://IP-DEL-ZIMA:3000
        ▼
 ┌──────────────┐  archivos   ┌─────────────┐  DWG→DXF (LibreDWG), PDF (texto u OCR),
 │  Open WebUI  │ ──────────▶ │  conversor  │  Word, Excel, PowerPoint, imágenes (OCR)
 │  (chat, RAG) │ ◀────────── │             │
 └──────┬───────┘   texto     └─────────────┘
        │ preguntas
        ▼
 ┌──────────────┐
 │    Ollama    │  modelo de chat (gemma3, qwen3...) + modelo de búsqueda (bge-m3)
 └──────────────┘
```

| Componente | Qué hace |
|---|---|
| **Ollama** | Ejecuta los modelos de IA en la CPU (o GPU NVIDIA si tienes). |
| **Open WebUI** | La página web para conversar, subir archivos y armar bases de conocimiento. |
| **conversor** (este repo) | Convierte cada archivo a texto. Es lo que permite que la IA "lea" un DWG. |

## 1. Requisitos

- Un equipo con ZimaOS y procesador x86-64 (ZimaBoard, ZimaCube o un PC armado).
- ~15 GB libres en disco para imágenes y modelos.
- RAM y tarjeta gráfica: definen qué modelo puedes usar.

| Equipo | `MODELO_CHAT` recomendado | Cómo se siente |
|---|---|---|
| 8 GB de RAM y/o tarjeta NVIDIA de 4 GB (p. ej. GTX 1050 Ti) | `qwen3:4b` (por defecto) | Con la tarjeta: respuestas en segundos. Solo con procesador: ~1 minuto. |
| 16 GB | `qwen3:8b` o `gemma3:12b` | Mejor comprensión de documentos largos; más lento. |
| 32 GB o más | `qwen3:30b` | Muy bueno y razonablemente rápido (solo activa una parte del modelo por palabra). |

**Tarjeta gráfica NVIDIA:** `instalar.sh` la detecta y la usa sola (archivo
`docker-compose.gpu.yml`). Para que funcione, ZimaOS debe tener el driver de NVIDIA: en la
terminal, `nvidia-smi` debe mostrar tu tarjeta. Si no la detecta, todo funciona igual, pero
usando solo el procesador.

## 2. Instalación

### Opción A — Terminal (recomendada)

1. Abre una terminal en el Zima. Por SSH desde tu PC:
   `ssh TU_USUARIO@IP-DEL-ZIMA` (mismo usuario y contraseña del panel de ZimaOS).
   Si no responde, activa el acceso SSH / modo desarrollador en la configuración de ZimaOS.
2. Descarga este proyecto e instálalo:

   ```sh
   sudo mkdir -p /DATA/AppData/ia-local && cd /DATA/AppData/ia-local
   curl -L https://github.com/JIF2012/IA-LOCAL/archive/refs/heads/main.tar.gz | sudo tar xz --strip-components=1
   sudo sh instalar.sh
   ```

   `instalar.sh` crea el archivo `.env` (con una clave aleatoria), descarga Ollama y Open WebUI,
   prepara el conversor y deja todo corriendo. Si la imagen del conversor no está publicada aún,
   la construye en el Zima (10-20 minutos la primera vez).

3. La primera vez se descargan los modelos (~5 GB). Puedes ver el avance con:

   ```sh
   sudo docker logs -f ia-descarga-modelos
   ```

   Cuando diga `Modelos listos.`, ya puedes usarla.

### Opción B — Desde la tienda de apps de ZimaOS

En el panel de ZimaOS: **App Store → + (instalar app personalizada) → Importar** y pega el
contenido de [`docker-compose.yml`](docker-compose.yml). Requiere que la imagen
`ghcr.io/jif2012/ia-local-conversor` esté publicada (la crea la acción de GitHub al hacer merge
a `main`; en GitHub → *Packages* → *ia-local-conversor* → *Package settings* déjala como
**Public**). Si la importación reclama por la línea `build: ./conversor`, bórrala.
En esta opción la clave del conversor queda con el valor por defecto; como el conversor no
se publica fuera de la red interna de Docker, es aceptable, pero la opción A es más segura.

## 3. Primer uso

1. Abre `http://IP-DEL-ZIMA:3000`.
2. Crea tu cuenta: **la primera cuenta queda como administrador**. Las siguientes quedan
   "pendientes" hasta que las apruebes (Panel de administración → Usuarios).
3. Elige el modelo arriba a la izquierda (ya viene seleccionado `MODELO_CHAT`).

### Preguntarle sobre un archivo

Arrastra el archivo al chat (o usa el botón **+** junto al cuadro de texto) y pregunta.
Ejemplos con un plano DWG:

- *¿Qué dice el cajetín? Dame proyecto, lámina, escala y fecha.*
- *¿Cuántas puertas y ventanas hay según los bloques insertados?*
- *Lista los recintos que aparecen en el plano.*
- *¿Cuál es la longitud total de la capa MUROS y el área de las polilíneas cerradas?*
- *Resume las notas generales del plano.*

Con PDF y Word: *resume este contrato*, *¿qué plazo y multas establece?*,
*¿qué hormigón especifican las EETT para fundaciones?*

> Por defecto la IA busca los trozos del documento más relacionados con tu pregunta. Para
> resúmenes de un documento completo, haz clic en el archivo adjunto y activa el uso del
> **documento completo** (si es muy largo puede no caber en el contexto del modelo).

### Base de conocimiento de una obra o proyecto

**Espacio de trabajo → Conocimiento → +**: crea por ejemplo "Edificio Los Álamos" y sube
todos sus planos, EETT, contratos y presupuestos (se puede subir una carpeta completa).
Luego en cualquier chat escribe `#` y elige esa colección: la IA responderá buscando en todos
esos documentos y citará de cuál sacó cada dato.

## 4. Qué entiende la IA de cada tipo de archivo

| Archivo | Qué se extrae |
|---|---|
| **PDF** | El texto de cada página. Las páginas escaneadas (sin texto) pasan por **OCR** en español. |
| **Word** `.docx` / `.doc` | Títulos, párrafos, listas, tablas, cuadros de texto, encabezado y pie. |
| **Excel** `.xlsx` / `.xls` | Cada hoja como tabla (valores calculados de las fórmulas). |
| **PowerPoint** `.pptx` | Texto, tablas y notas de cada diapositiva. |
| **Imágenes** | OCR (fotos de documentos, escaneos `.tif`), al subirlas a una base de conocimiento. |
| **DWG / DXF** | Ver abajo. |
| Texto, CSV, Markdown, código | Tal cual. |

### Planos DWG / DXF

La IA **no ve el dibujo**: el conversor recorre el plano y le entrega un resumen escrito con:

- **Datos del archivo**: versión de AutoCAD, unidades, fecha de modificación, presentaciones (láminas).
- **Cajetín y atributos**: los valores de los bloques con atributos (proyecto, lámina, escala, revisión, rótulos de recintos...).
- **Textos** (TEXT, MTEXT, multidirectrices) agrupados por espacio modelo / presentación y por capa, ordenados de arriba hacia abajo.
- **Textos dentro de bloques** (cajetines, tablas, simbologías).
- **Cotas** con su medida, por capa.
- **Conteo de bloques** insertados (puertas, ventanas, artefactos sanitarios, símbolos...).
- **Capas**: cantidad de elementos, longitud total dibujada y área de las polilíneas cerradas
  (en metros cuando el dibujo está en mm, cm o m).

Limitaciones:

- Lee DWG desde AutoCAD R13 hasta el formato 2018, que es el que siguen usando las versiones
  actuales de AutoCAD. Si un DWG falla, ábrelo en AutoCAD y guárdalo como **DXF**: el DXF se lee directo.
- Las referencias externas (XREF) no se incluyen; se listan para que sepas que faltan.
- Las áreas solo salen de polilíneas cerradas (no de sombreados ni regiones).
- Objetos propios de verticales (Civil 3D, Architecture) pueden no leerse.

Para ver exactamente qué recibe la IA de un archivo que está en el NAS:

```sh
sudo docker exec ia-conversor convertir "/datos/Documents/Proyecto/planta.dwg"
```

(`/datos` es la carpeta `/DATA` del Zima, montada solo lectura.)

## 5. Configuración

Edita `/DATA/AppData/ia-local/.env` y vuelve a ejecutar `sudo sh instalar.sh`.

| Variable | Por defecto | Para qué |
|---|---|---|
| `MODELO_CHAT` | `qwen3:4b` | Modelo que responde. Ver tabla de requisitos. |
| `MODELO_EMBEDDINGS` | `bge-m3` | Modelo que indexa documentos (multilingüe). |
| `CONTEXTO_TOKENS` | `8192` | Cuánto texto lee el modelo de una vez. Bájalo a 4096 si falta RAM. |
| `PUERTO_WEB` | `3000` | Puerto de la interfaz web. |
| `CONVERSOR_API_KEY` | aleatoria | Clave entre Open WebUI y el conversor. |

Ajustes del conversor (en `docker-compose.yml`, servicio `conversor` → `environment`):

| Variable | Por defecto | Para qué |
|---|---|---|
| `OCR_ACTIVADO` | `true` | OCR para PDF escaneados e imágenes. |
| `OCR_IDIOMAS` | `spa+eng` | Idiomas de Tesseract. |
| `OCR_MAX_PAGINAS` | `100` | Máximo de páginas con OCR por documento. |
| `DWG_MAX_TEXTOS` | `5000` | Máximo de líneas de texto por plano (planos topográficos enormes). |
| `HOJA_MAX_FILAS` | `5000` | Máximo de filas por hoja de Excel. |
| `CONVERSOR_CONCURRENCIA` | `2` | Archivos procesados en paralelo. |

> **Importante:** Open WebUI guarda su configuración la primera vez que arranca. Si después
> cambias `MODELO_EMBEDDINGS`, `CONVERSOR_API_KEY` u otro ajuste de documentos en `.env`, cámbialo
> también en **Panel de administración → Configuración → Documentos** (o no tendrá efecto).

**Cambiar de modelo de chat** sin tocar archivos: Panel de administración → Configuración →
Modelos → descargar (escribe por ejemplo `gemma3:12b`). Hay más modelos en <https://ollama.com/library>.

## 6. Solución de problemas

| Problema | Qué hacer |
|---|---|
| Al subir un archivo: `Error loading document: 401` | La clave no coincide. Copia `CONVERSOR_API_KEY` de `.env` en Panel de administración → Configuración → Documentos → clave del cargador externo. |
| `Error loading document: 422 ...` | El archivo no se pudo leer; el mensaje explica por qué (PDF con contraseña, DWG dañado, etc.). |
| Responde que no encuentra la información | Usa el documento completo (ver arriba) o haz preguntas más específicas; en planos, nombra la capa o el bloque. |
| Muy lento o se corta | Usa un modelo más pequeño o baja `CONTEXTO_TOKENS`. |
| Ver qué pasa | `sudo docker logs ia-conversor`, `sudo docker logs ia-open-webui`, `sudo docker logs ia-ollama` |

Estado del conversor (debe mostrar `"dwg2dxf": true` y `"tesseract": true`):

```sh
sudo docker exec ia-conversor python -c "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:8000/health').read().decode())"
```

## 7. Actualizar y respaldar

```sh
cd /DATA/AppData/ia-local
curl -L https://github.com/JIF2012/IA-LOCAL/archive/refs/heads/main.tar.gz | sudo tar xz --strip-components=1
sudo sh instalar.sh
```

Todo lo importante (usuarios, chats, bases de conocimiento, modelos) queda en
`/DATA/AppData/ia-local/`: respalda esa carpeta.

**Seguridad:** úsala dentro de tu red local. No abras el puerto 3000 hacia internet en el
router; para acceso remoto usa una VPN (por ejemplo la conexión remota de ZimaOS o Tailscale).

## 8. Desarrollo

```
conversor/
  conversor/app.py              API para Open WebUI (PUT /process, GET /health)
  conversor/__main__.py         comando "convertir"
  conversor/extractores/cad.py  DWG/DXF (LibreDWG + ezdxf)
  conversor/extractores/pdf.py  PDF (PyMuPDF + OCR Tesseract)
  conversor/extractores/office.py  Word, Excel, PowerPoint
  tests/                        pruebas (pytest)
```

Pruebas dentro de la imagen (incluye la conversión real de DWG con LibreDWG):

```sh
docker build -t ia-local-conversor conversor
docker run --rm --user root -v "$PWD/conversor/tests:/app/tests:ro" ia-local-conversor \
  sh -c "pip install -q pytest httpx && python -m pytest -q /app/tests"
```
