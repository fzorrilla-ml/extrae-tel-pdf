#!/usr/bin/env python3
# extrae_tel_pdf_ocr.py — Extrae teléfono RD y crea copia del PDF nombrada con solo dígitos (sobrescribe si existe)
# Uso (genérico):  extrae_tel_pdf <archivo.pdf>
# Dep.: pdfminer.six, PyMuPDF (fitz), pytesseract, Tesseract OCR (binario)
# Nota: empaquetable a .exe con PyInstaller; incluye Tesseract dentro del bundle.

import sys, os, re, unicodedata, io, shutil
from typing import Optional, Tuple, List

# ─────────────────────────────────────────────────────────────────────────────
# Rutas cuando está empacado con PyInstaller (onefile)
BUNDLE_BASE = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))
TESS_DIR = os.path.join(BUNDLE_BASE, "tesseract")            # carpeta con tesseract.exe y subcarpeta tessdata
TESSDATA_DIR = os.path.join(TESS_DIR, "tessdata")            # ← corrección clave
TESS_EXE = os.path.join(TESS_DIR, "tesseract.exe")

# Si existe el Tesseract empacado, configúralo
try:
    import pytesseract
    if os.path.exists(TESS_EXE):
        # Asegurar rutas correctas para los modelos
        os.environ["TESSDATA_PREFIX"] = TESSDATA_DIR
        pytesseract.pytesseract.tesseract_cmd = TESS_EXE
except Exception:
    pass

# ─────────────────────────────────────────────────────────────────────────────
# Regex teléfono RD: opcional +1, códigos 809/829/849, separadores comunes
PHONE_RE = re.compile(
    r'(?<!\d)(?:\+?1[\s\-.]?)?\(?(?:809|829|849)\)?[\s\-.]?\d{3}[\s\-.]?\d{4}(?!\d)'
)

def normalize(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c)).lower()

# ─────────────────────────────────────────────────────────────────────────────
# Paso 1: intentar texto nativo PDF (pdfminer) en esquina superior derecha
def try_pdf_text(pdf_path: str, width_frac=0.40, height_frac=0.25) -> Optional[str]:
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTPage, LTTextContainer, LTTextLine

    pages = extract_pages(pdf_path, maxpages=1)
    page_layout = None
    for obj in pages:
        if isinstance(obj, LTPage):
            page_layout = obj
            break
    if not page_layout:
        return None

    W, H = page_layout.width, page_layout.height
    x_min, y_min = W * (1 - width_frac), H * (1 - height_frac)
    lines: List[Tuple[float,float,str]] = []

    def visit(container):
        if isinstance(container, LTTextContainer):
            for line in container:
                if isinstance(line, LTTextLine):
                    x0, y0, x1, y1 = line.bbox
                    if (x1 >= x_min) and (y1 >= y_min):  # interseca esquina sup. derecha
                        t = line.get_text().strip()
                        if t:
                            lines.append((y1, x0, t))
        if hasattr(container, "__iter__"):
            for child in container:
                visit(child)

    visit(page_layout)
    lines.sort(key=lambda t: (-t[0], t[1]))
    if not lines:
        return None

    for i, (_y, _x, raw) in enumerate(lines):
        if "numero" in normalize(raw) and "asignado" in normalize(raw):
            tail = raw.split(":", 1)[1] if ":" in raw else ""
            candidate = (tail + " " + (lines[i+1][2] if i+1 < len(lines) else "")).strip()
            m = PHONE_RE.search(candidate) or PHONE_RE.search(" ".join(l[2] for l in lines[i:]))
            if m:
                return m.group(0).strip()
    return None

# ─────────────────────────────────────────────────────────────────────────────
# Paso 2: OCR de la esquina superior derecha (si el PDF es imagen)
def ocr_top_right(pdf_path: str, width_frac=0.40, height_frac=0.25) -> Optional[str]:
    import fitz  # PyMuPDF
    from PIL import Image, ImageOps, ImageFilter
    import pytesseract

    # Forzar el modelo a encontrar 'spa/eng' en el path correcto
    tess_cfg = f'--psm 6 --oem 3 --tessdata-dir "{TESSDATA_DIR}"'

    doc = fitz.open(pdf_path)
    if len(doc) == 0:
        return None
    page = doc[0]

    # Render con zoom para mejor OCR
    zoom = 2.0
    mat = fitz.Matrix(zoom, zoom)
    pm = page.get_pixmap(matrix=mat)
    img = Image.open(io.BytesIO(pm.tobytes("png")))

    W, H = img.size
    x0, y0 = int(W*(1-width_frac)), 0
    x1, y1 = W, int(H*height_frac)
    crop = img.crop((x0, y0, x1, y1))

    # Pre-procesado suave
    scale = 1.5
    crop = crop.resize((int(crop.width*scale), int(crop.height*scale)), Image.LANCZOS)
    gray = ImageOps.grayscale(crop)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1.2, percent=150, threshold=3))

    # OCR por palabras para ubicar la línea
    data = pytesseract.image_to_data(
        gray, lang="spa+eng",
        config=tess_cfg,
        output_type=pytesseract.Output.DICT
    )
    n = len(data["text"])
    lines = {}
    for i in range(n):
        try:
            if int(data["conf"][i]) < 0:
                continue
        except Exception:
            continue
        ln = (data["page_num"][i], data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(ln, []).append((data["left"][i], data["text"][i]))

    for k in lines:
        lines[k].sort(key=lambda t: t[0])  # ordenar tokens por X

    # Buscar la línea con "Número asignado"
    keys_sorted = sorted(lines.keys())
    for idx, k in enumerate(keys_sorted):
        tokens = [t[1] for t in lines[k] if t[1].strip()]
        if not tokens:
            continue
        raw_line = " ".join(tokens)
        norm_line = normalize(raw_line)
        if "numero" in norm_line and "asignado" in norm_line:
            tail = raw_line.split(":", 1)[1] if ":" in raw_line else ""
            next_key = keys_sorted[idx+1] if (idx+1 < len(keys_sorted)) else None
            next_text = " ".join([t for _, t in lines[next_key]]) if next_key else ""
            candidate = (tail + " " + next_text).strip()
            m = PHONE_RE.search(candidate)
            if m:
                return m.group(0).strip()

    # Fallback: OCR global del recorte y regex
    text = pytesseract.image_to_string(gray, lang="spa+eng", config=tess_cfg)
    pos = normalize(text).find("numero asignado")
    if pos >= 0:
        tail = text[pos: pos+500]
        m = PHONE_RE.search(tail)
        if m:
            return m.group(0).strip()
    return None

# ─────────────────────────────────────────────────────────────────────────────
def digits_only(s: str) -> str:
    return re.sub(r'\D', '', s)

def copy_pdf_with_digits_name(src_pdf: str, phone: str) -> str:
    """
    Crea/reescribe la copia del PDF en la misma carpeta del original,
    con nombre solo-dígitos: <digits>.pdf (sobrescribe si existe).
    Devuelve la ruta creada.
    """
    out_dir = os.path.dirname(os.path.abspath(src_pdf))
    digits = digits_only(phone)
    if not digits:
        raise ValueError("El teléfono extraído no contiene dígitos.")
    dst_path = os.path.join(out_dir, f"{digits}.pdf")
    shutil.copyfile(src_pdf, dst_path)  # sobrescribe si existe
    return dst_path

# ─────────────────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) != 2:
        print("Uso: extrae_tel_pdf <archivo.pdf>", file=sys.stderr)
        sys.exit(2)
    pdf_path = sys.argv[1]
    if not os.path.isfile(pdf_path) or not pdf_path.lower().endswith(".pdf"):
        print("ERROR: Debe indicar un archivo .pdf existente.", file=sys.stderr)
        sys.exit(2)

    # 1) Intento rápido por texto nativo
    try:
        phone = try_pdf_text(pdf_path)
    except Exception:
        phone = None

    # 2) Fallback OCR si no hubo texto
    if not phone:
        try:
            phone = ocr_top_right(pdf_path)
        except Exception as e:
            print(f"ERROR OCR: {e}", file=sys.stderr)
            sys.exit(1)

    if not phone:
        print("ERROR: No se encontró 'Número asignado:' con teléfono en la esquina superior derecha.", file=sys.stderr)
        sys.exit(3)

    # 3) Crear/reescribir copia con nombre de solo dígitos
    try:
        _dst = copy_pdf_with_digits_name(pdf_path, phone)
    except Exception as e:
        print(f"ERROR al crear/reescribir la copia del PDF: {e}", file=sys.stderr)
        print(phone)
        sys.exit(4)

    # 4) Imprimir SOLO el número (para integraciones por consola)
    print(phone)
    sys.exit(0)

# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
