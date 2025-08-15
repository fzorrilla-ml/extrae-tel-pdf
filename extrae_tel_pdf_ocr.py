#!/usr/bin/env python3
# extrae_tel_pdf_ocr.py — Extrae teléfono RD y crea copia del PDF nombrada con solo dígitos (sobrescribe si existe)
# Uso:  python extrae_tel_pdf_ocr.py archivo.pdf
#
# Este script lee la primera página de un PDF, busca el texto "Número asignado:" en la esquina superior derecha
# y extrae el número de teléfono dominicano que sigue a esta etiqueta. Si el PDF es imagen, utiliza OCR
# mediante Tesseract. Posteriormente crea una copia del PDF original en la misma carpeta con el nombre
# compuesto únicamente por los dígitos del teléfono (p.ej. 8495072495.pdf), sobrescribiendo cualquier
# archivo existente con ese nombre.
#
# Dependencias de Python:
#   - pdfminer.six: para extraer texto posicional de PDFs nativos.
#   - PyMuPDF (fitz): para renderizar páginas en imagen (utilizado por el OCR).
#   - pytesseract: enlace con el motor Tesseract OCR.
#   - Pillow: manipulaciones de imagen (instalado implícitamente con pytesseract).
#
# Nota sobre Tesseract:
# El script intenta localizar un binario de Tesseract empaquetado junto al ejecutable generado por
# PyInstaller (ver configuración en el workflow de GitHub Actions). Si se distribuye como script,
# se asume que Tesseract está disponible en el PATH o que se especifica mediante pytesseract.pytesseract.tesseract_cmd.

import sys
import os
import re
import unicodedata
import io
import shutil
from typing import Optional, Tuple, List

# ────────────────────────────────────────────────────────────────────
# Configuración opcional para Tesseract empaquetado en PyInstaller.
# Cuando PyInstaller ejecuta el binario, crea un directorio temporal accesible
# mediante el atributo _MEIPASS. Guardamos Tesseract (binario y datos) dentro de
# una subcarpeta llamada "tesseract" y configuramos las variables de entorno
# apropiadas para pytesseract.

BUNDLE_BASE = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))
TESS_DIR = os.path.join(BUNDLE_BASE, "tesseract")
TESS_EXE = os.path.join(TESS_DIR, "tesseract.exe")

try:
    import pytesseract
    if os.path.exists(TESS_EXE):
        # Apuntar a los datos de entrenamiento dentro del bundle
        os.environ["TESSDATA_PREFIX"] = TESS_DIR
        # Indicarle a pytesseract el ejecutable incluido
        pytesseract.pytesseract.tesseract_cmd = TESS_EXE
except Exception:
    # Si pytesseract no está disponible aún, lo importaremos dinámicamente más adelante
    pass

# ────────────────────────────────────────────────────────────────
# Expresión regular para extraer teléfonos de República Dominicana. Esta expresión
# acepta opcionalmente el prefijo +1, códigos de área 809/829/849 (con o sin
# paréntesis) y separadores comunes (espacio, punto o guion) entre las partes.
PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?1[\s\-.]?)?\(? (?:809|829|849) \)?[\s\-.]?\d{3}[\s\-.]?\d{4}(?!\d)",
    re.VERBOSE,
)


def normalize(text: str) -> str:
    """Normaliza texto eliminando acentos y convirtiendo a minúsculas."""
    return "".join(
        c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)
    ).lower()


# ────────────────────────────────────────────────────────────────
# Extracción de texto nativo con pdfminer

def try_pdf_text(
    pdf_path: str, width_frac: float = 0.40, height_frac: float = 0.25
) -> Optional[str]:
    """
    Intenta extraer texto nativo de la primera página del PDF usando pdfminer.
    Se limita a la esquina superior derecha según las fracciones indicadas.

    Args:
        pdf_path: Ruta al PDF.
        width_frac: Fracción del ancho de la página que corresponde a la zona de búsqueda (por defecto 40%).
        height_frac: Fracción de la altura de la página que corresponde a la zona de búsqueda (por defecto 25%).

    Returns:
        El número de teléfono encontrado como cadena o None si no se detecta.
    """
    try:
        from pdfminer.high_level import extract_pages
        from pdfminer.layout import LTPage, LTTextContainer, LTTextLine
    except ImportError:
        return None

    pages = extract_pages(pdf_path, maxpages=1)
    page_layout: Optional["LTPage"] = None
    for obj in pages:
        if hasattr(obj, "width") and hasattr(obj, "height"):
            page_layout = obj  # type: ignore
            break
    if not page_layout:
        return None

    W, H = page_layout.width, page_layout.height
    x_min = W * (1.0 - width_frac)
    y_min = H * (1.0 - height_frac)
    lines: List[Tuple[float, float, str]] = []

    def visit(container):
        # Recorremos contenedores de texto y sus líneas
        from pdfminer.layout import LTTextContainer, LTTextLine

        if isinstance(container, LTTextContainer):
            for line in container:
                if isinstance(line, LTTextLine):
                    x0, y0, x1, y1 = line.bbox
                    # Comprobar intersección con la zona delimitada
                    if x1 >= x_min and y1 >= y_min:
                        txt = line.get_text().strip()
                        if txt:
                            lines.append((y1, x0, txt))
        # Descender a hijos
        if hasattr(container, "__iter__"):
            for child in container:
                visit(child)

    visit(page_layout)
    # Ordenar de arriba hacia abajo (y descendente) y luego por x ascendente
    lines.sort(key=lambda t: (-t[0], t[1]))
    if not lines:
        return None

    for i, (_y, _x, raw) in enumerate(lines):
        norm = normalize(raw)
        if "numero" in norm and "asignado" in norm:
            # Extraer la parte después de los dos puntos si existe
            tail = raw.split(":", 1)[1] if ":" in raw else ""
            candidate = (
                tail + " " + (lines[i + 1][2] if i + 1 < len(lines) else "")
            ).strip()
            m = PHONE_RE.search(candidate) or PHONE_RE.search(
                " ".join(l[2] for l in lines[i:])
            )
            if m:
                return m.group(0).strip()
    return None


# ────────────────────────────────────────────────────────────────
# OCR en esquina superior derecha con PyMuPDF y pytesseract

def ocr_top_right(
    pdf_path: str, width_frac: float = 0.40, height_frac: float = 0.25
) -> Optional[str]:
    """
    Si el PDF es una imagen (sin texto nativo), renderiza la primera página a una imagen,
    recorta la esquina superior derecha y aplica OCR para buscar el número de teléfono.

    Args:
        pdf_path: Ruta al PDF.
        width_frac: Fracción del ancho de la página considerada como esquina derecha.
        height_frac: Fracción de la altura de la página considerada como parte superior.

    Returns:
        El número de teléfono encontrado o None si no se localiza.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return None
    try:
        from PIL import Image, ImageOps, ImageFilter
    except ImportError:
        return None
    try:
        import pytesseract
    except ImportError:
        return None

    # Ajustar la ruta del ejecutable de Tesseract si está empaquetado
    if os.path.exists(TESS_EXE):
        pytesseract.pytesseract.tesseract_cmd = TESS_EXE
        os.environ["TESSDATA_PREFIX"] = TESS_DIR

    doc = fitz.open(pdf_path)
    if doc.page_count == 0:
        return None
    page = doc[0]
    # Renderizar con zoom para obtener mayor resolución
    zoom = 2.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    img = Image.open(io.BytesIO(pix.tobytes("png")))

    W, H = img.size
    x0, y0 = int(W * (1.0 - width_frac)), 0
    x1, y1 = W, int(H * height_frac)
    crop = img.crop((x0, y0, x1, y1))
    # Escalar para mejorar OCR y aplicar filtros de nitidez
    scale = 1.5
    crop = crop.resize(
        (int(crop.width * scale), int(crop.height * scale)), Image.LANCZOS
    )
    gray = ImageOps.grayscale(crop)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1.2, percent=150, threshold=3))

    # OCR detallado por líneas
    data = pytesseract.image_to_data(
        gray,
        lang="spa+eng",
        config="--psm 6 --oem 3",
        output_type=pytesseract.Output.DICT,
    )
    n = len(data.get("text", []))
    lines: dict = {}
    for i in range(n):
        try:
            conf = int(data["conf"][i])
        except Exception:
            conf = -1
        if conf < 0:
            continue
        line_id = (
            data.get("page_num", [])[i],
            data.get("block_num", [])[i],
            data.get("par_num", [])[i],
            data.get("line_num", [])[i],
        )
        lines.setdefault(line_id, []).append((data.get("left", [])[i], data["text"][i]))

    # Ordenar tokens en cada línea
    for k in lines:
        lines[k].sort(key=lambda t: t[0])

    keys_sorted = sorted(lines.keys())
    for idx, k in enumerate(keys_sorted):
        tokens = [t[1] for t in lines[k] if t[1].strip()]
        if not tokens:
            continue
        raw_line = " ".join(tokens)
        norm_line = normalize(raw_line)
        if "numero" in norm_line and "asignado" in norm_line:
            tail = raw_line.split(":", 1)[1] if ":" in raw_line else ""
            next_key = keys_sorted[idx + 1] if (idx + 1) < len(keys_sorted) else None
            next_text = (
                " ".join([t[1] for t in lines[next_key]]) if next_key else ""
            )
            candidate = (tail + " " + next_text).strip()
            m = PHONE_RE.search(candidate)
            if m:
                return m.group(0).strip()
    # Fallback: OCR libre del recorte
    text = pytesseract.image_to_string(
        gray, lang="spa+eng", config="--psm 6 --oem 3"
    )
    pos = normalize(text).find("numero asignado")
    if pos >= 0:
        tail = text[pos : pos + 500]
        m = PHONE_RE.search(tail)
        if m:
            return m.group(0).strip()
    return None


def digits_only(s: str) -> str:
    """Extrae únicamente los dígitos de una cadena."""
    return re.sub(r"\D", "", s)


def copy_pdf_with_digits_name(src_pdf: str, phone: str) -> str:
    """
    Crea o sobrescribe una copia del PDF en la misma carpeta del original con
    nombre formado únicamente por los dígitos del teléfono y extensión .pdf.

    Args:
        src_pdf: Ruta al PDF de origen.
        phone: Número de teléfono extraído.

    Returns:
        La ruta al archivo creado.
    """
    out_dir = os.path.dirname(os.path.abspath(src_pdf))
    digits = digits_only(phone)
    if not digits:
        raise ValueError("El teléfono extraído no contiene dígitos.")
    dst_path = os.path.join(out_dir, f"{digits}.pdf")
    shutil.copyfile(src_pdf, dst_path)
    return dst_path


def main() -> None:
    if len(sys.argv) != 2:
        print("Uso: python extrae_tel_pdf_ocr.py <archivo.pdf>", file=sys.stderr)
        sys.exit(2)
    pdf_path = sys.argv[1]
    if not os.path.isfile(pdf_path) or not pdf_path.lower().endswith(".pdf"):
        print("ERROR: Debe indicar un archivo .pdf existente.", file=sys.stderr)
        sys.exit(2)

    phone: Optional[str] = None
    # Intentar extracción de texto nativo
    try:
        phone = try_pdf_text(pdf_path)
    except Exception:
        phone = None
    # Si no se encontró, hacer OCR
    if not phone:
        try:
            phone = ocr_top_right(pdf_path)
        except Exception as e:
            print(f"ERROR OCR: {e}", file=sys.stderr)
            sys.exit(1)
    if not phone:
        print(
            "ERROR: No se encontró 'Número asignado:' con teléfono en la esquina superior derecha.",
            file=sys.stderr,
        )
        sys.exit(3)
    # Copiar el PDF con nombre de dígitos
    try:
        _dst = copy_pdf_with_digits_name(pdf_path, phone)
    except Exception as e:
        print(f"ERROR al crear/reescribir la copia del PDF: {e}", file=sys.stderr)
        print(phone)
        sys.exit(4)
    # Imprimir sólo el número extraído
    print(phone)
    sys.exit(0)


if __name__ == "__main__":
    main()
