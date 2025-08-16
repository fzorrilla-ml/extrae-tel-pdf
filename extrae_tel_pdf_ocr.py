#!/usr/bin/env python3
# Extrae el teléfono RD desde la esquina superior derecha (tras "Número asignado:")
# e imprime el número (solo dígitos). Además crea/actualiza una copia del PDF
# en el mismo directorio, con nombre = <solo_digitos>.pdf (sobrescribe si existe).

import sys, os, re, io, shutil, unicodedata
from pathlib import Path
from typing import Optional, Tuple
import fitz  # PyMuPDF
from PIL import Image
import pytesseract

# -------------------- utilidades de rutas (ejecución normal o PyInstaller onefile)
def _base_dir() -> Path:
    if getattr(sys, "frozen", False):  # ejecutable (PyInstaller)
        return Path(sys.executable).parent
    return Path(__file__).parent

def resolve_tessdata_dir() -> Path:
    """
    Busca 'tessdata' en:
      1) TESSDATA_PREFIX (si existe y contiene modelos)
      2) ./tessdata junto al .exe/.py
      3) sys._MEIPASS/tessdata (si algún día se usa --add-data)
    """
    cands = []
    env = os.environ.get("TESSDATA_PREFIX")
    if env:
        cands.append(Path(env))
    cands.append(_base_dir() / "tessdata")
    if hasattr(sys, "_MEIPASS"):
        cands.append(Path(sys._MEIPASS) / "tessdata")

    for p in cands:
        if (p / "eng.traineddata").exists() and (p / "spa.traineddata").exists():
            return p
    # último recurso: retorna ./tessdata (servirá para que el error sea claro si faltan modelos)
    return _base_dir() / "tessdata"

def resolve_tesseract_cmd() -> str:
    """
    Si incluimos binarios en ./tesseract (tesseract.exe + DLLs), úsalos.
    De lo contrario, usa 'tesseract' del PATH del sistema.
    """
    cand = _base_dir() / "tesseract" / "tesseract.exe"
    if cand.exists():
        return str(cand)
    return "tesseract"

# -------------------- normalización y regex
def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

RD_REGEX = re.compile(
    r"""
    (?:\+?\s*1[\s\-\.]*)?           # opcional +1
    (?:\(?\s*8(?:09|29|49)\s*\)?    # 809/829/849 con o sin paréntesis
     [\s\-\.]*)                     # separadores
    \d{3}[\s\-\.]*\d{4}             # 7 dígitos restantes con separadores opcionales
    """,
    re.VERBOSE,
)

def digits_only(s: str) -> str:
    return re.sub(r"\D", "", s)

# -------------------- OCR en esquina superior derecha
def ocr_top_right_phone(pdf_path: Path) -> Optional[str]:
    doc = fitz.open(str(pdf_path))
    if doc.page_count == 0:
        return None
    page = doc.load_page(0)
    rect = page.rect

    # recorte: esquina superior derecha (ajustable)
    # ancho ~45% derecha, alto ~35% superior
    crop = fitz.Rect(rect.width * 0.55, rect.y0, rect.x1, rect.height * 0.35)

    # renderizamos a imagen con buena resolución
    zoom = 2.0  # ~144 dpi*2 -> ~288 dpi
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, clip=crop, alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    # configurar Tesseract
    tessdir = resolve_tessdata_dir()
    os.environ["TESSDATA_PREFIX"] = str(tessdir)
    pytesseract.pytesseract.tesseract_cmd = resolve_tesseract_cmd()

    # OCR (español + inglés; psm 6 = bloque de texto uniforme)
    text = pytesseract.image_to_string(img, lang="spa+eng", config="--psm 6").strip()

    # buscamos la frase y luego el teléfono
    norm = _strip_accents(text).lower()
    clave = _strip_accents("Número asignado:").lower()
    telefono = None

    if clave in norm:
        after = text[norm.index(clave) + len(clave):]
        # tomar hasta fin de línea/primer salto
        first_line = after.splitlines()[0] if after else ""
        m = RD_REGEX.search(first_line)
        if not m:
            # fallback: buscar en el resto del bloque
            m = RD_REGEX.search(after)
        if m:
            telefono = m.group(0)
    else:
        # fallback: buscar en todo el bloque por si el OCR omitió la frase
        m = RD_REGEX.search(text)
        if m:
            telefono = m.group(0)

    if not telefono:
        return None

    # normalizamos a 10 dígitos para RD (quitando +1 si vino)
    d = digits_only(telefono)
    if len(d) >= 10:
        d = d[-10:]
    return d

# -------------------- copia del PDF con nombre = <solo_digitos>.pdf (sobrescribe)
def copy_pdf_with_digits_name(src: Path, digits: str) -> Path:
    dest = src.parent / f"{digits}.pdf"
    # shutil.copyfile sobrescribe si existe
    shutil.copyfile(src, dest)
    return dest

# -------------------- CLI
def main(argv: list) -> int:
    if len(argv) < 2:
        print("Uso: extrae_tel_pdf <archivo.pdf>", file=sys.stderr)
        return 1

    pdf_path = Path(argv[1])
    if not pdf_path.exists():
        print(f"Error: no existe {pdf_path}", file=sys.stderr)
        return 1

    try:
        phone = ocr_top_right_phone(pdf_path)
    except Exception as e:
        print(f"ERROR OCR: {e}", file=sys.stderr)
        return 1

    if not phone:
        print("ERROR: No se pudo extraer el teléfono.", file=sys.stderr)
        return 2

    # imprime solo dígitos
    print(phone)

    # crea/sobrescribe copia con nombre = <solo_digitos>.pdf
    try:
        copy_pdf_with_digits_name(pdf_path, phone)
    except Exception as e:
        print(f"ERROR al copiar el PDF: {e}", file=sys.stderr)
        return 3

    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
