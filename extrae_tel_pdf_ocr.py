#!/usr/bin/env python3
# Lee un PDF, extrae el teléfono RD en la esquina superior derecha tras "Número asignado:",
# imprime SOLO dígitos y crea/actualiza una copia del PDF con nombre <digitos>.pdf.

import sys, os, re, shutil, unicodedata
from pathlib import Path
from typing import Optional
import fitz  # PyMuPDF
from PIL import Image
import pytesseract

# -------------------- Paths robustos (fuente o PyInstaller onefile)
def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent

def resolve_tessdata_dir() -> Path:
    """
    Busca 'tessdata' en:
      1) TESSDATA_PREFIX (si apunta a modelos válidos)
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
    return _base_dir() / "tessdata"

def resolve_tesseract_cmd() -> str:
    """
    Usa .\tesseract\tesseract.exe si existe al lado del .exe/.py;
    si no, deja 'tesseract' para que use el del sistema (PATH).
    """
    cand = _base_dir() / "tesseract" / "tesseract.exe"
    if cand.exists():
        return str(cand)
    return "tesseract"

# -------------------- Utilidades
def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")

RD_REGEX = re.compile(
    r"""
    (?:\+?\s*1[\s\-\.]*)?           # opcional +1
    (?:\(?\s*8(?:09|29|49)\s*\)?    # 809/829/849 con o sin paréntesis
     [\s\-\.]*)                     # separadores
    \d{3}[\s\-\.]*\d{4}             # 7 dígitos restantes
    """,
    re.VERBOSE,
)

def digits_only(s: str) -> str:
    return re.sub(r"\D", "", s)

# -------------------- OCR esquina superior derecha
def ocr_top_right_phone(pdf_path: Path) -> Optional[str]:
    doc = fitz.open(str(pdf_path))
    if doc.page_count == 0:
        return None
    page = doc.load_page(0)
    rect = page.rect

    # Recorte: 45% derecha x 35% superior (ajustable si hace falta)
    crop = fitz.Rect(rect.width * 0.55, rect.y0, rect.x1, rect.height * 0.35)

    # Render a ~288 dpi para buen OCR
    zoom = 2.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, clip=crop, alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    # Configurar Tesseract
    tessdir = resolve_tessdata_dir()
    os.environ["TESSDATA_PREFIX"] = str(tessdir)
    pytesseract.pytesseract.tesseract_cmd = resolve_tesseract_cmd()

    # OCR (español+inglés)
    text = pytesseract.image_to_string(img, lang="spa+eng", config="--psm 6").strip()

    norm = _strip_accents(text).lower()
    clave = _strip_accents("Número asignado:").lower()

    telefono = None
    if clave in norm:
        after = text[norm.index(clave) + len(clave):]
        first_line = after.splitlines()[0] if after else ""
        m = RD_REGEX.search(first_line) or RD_REGEX.search(after)
        if m:
            telefono = m.group(0)
    else:
        # Fallback: por si el OCR omitió la frase
        m = RD_REGEX.search(text)
        if m:
            telefono = m.group(0)

    if not telefono:
        return None

    d = digits_only(telefono)
    if len(d) >= 10:
        d = d[-10:]  # conserva 10 dígitos finales (RD)
    return d

# -------------------- Copia PDF con nombre = <digitos>.pdf (sobrescribe)
def copy_pdf_with_digits_name(src: Path, digits: str) -> Path:
    dest = src.parent / f"{digits}.pdf"
    shutil.copyfile(src, dest)  # sobrescribe si existe
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

    print(phone)  # stdout: solo dígitos

    try:
        copy_pdf_with_digits_name(pdf_path, phone)
    except Exception as e:
        print(f"ERROR al copiar el PDF: {e}", file=sys.stderr)
        return 3

    return 0

if __name__ == "__main__":
    sys.exit(main(sys.argv))
