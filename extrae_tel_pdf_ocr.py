#!/usr/bin/env python3
# extrae_tel_pdf_ocr.py — Extrae teléfono RD y crea copia del PDF (sobrescribe)
# Uso (genérico):  extrae_tel_pdf <archivo.pdf>
# Dep.: pdfminer.six, PyMuPDF (fitz), pytesseract, Tesseract OCR (binario)
import sys, os, re, unicodedata, io, shutil
from typing import Optional, Tuple, List

# ── Resolución de rutas (PyInstaller onefile o ejecución local)
BUNDLE_BASE = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))
TESS_DIR     = os.path.join(BUNDLE_BASE, "tesseract")             # contiene tesseract.exe
TESSDATA_DIR = os.path.join(TESS_DIR, "tessdata")                 # contiene *.traineddata
TESS_EXE     = os.path.join(TESS_DIR, "tesseract.exe")

def _resolve_tessdata_dir() -> Optional[str]:
    """Elige el mejor tessdata disponible."""
    # 1) Si viene empacado con el exe
    if os.path.isdir(TESSDATA_DIR) and any(f.endswith(".traineddata") for f in os.listdir(TESSDATA_DIR)):
        return TESSDATA_DIR
    # 2) Si el usuario definió TESSDATA_PREFIX fuera
    env = os.environ.get("TESSDATA_PREFIX")
    if env and os.path.isdir(env):
        return env
    # 3) Si hay tessdata junto al ejecutable/script (ejecución local de prueba)
    local_tess = os.path.join(os.path.abspath(os.path.dirname(__file__)), "tessdata")
    if os.path.isdir(local_tess) and any(f.endswith(".traineddata") for f in os.listdir(local_tess)):
        return local_tess
    return None

# Configurar pytesseract / Tesseract
try:
    import pytesseract
    if os.path.exists(TESS_EXE):
        pytesseract.pytesseract.tesseract_cmd = TESS_EXE
    _td = _resolve_tessdata_dir()
    if _td:
        os.environ["TESSDATA_PREFIX"] = _td
except Exception:
    pass

PHONE_RE = re.compile(r'(?<!\d)(?:\+?1[\s\-.]?)?\(?(?:809|829|849)\)?[\s\-.]?\d{3}[\s\-.]?\d{4}(?!\d)')

def normalize(s: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c)).lower()

# ───────────────────────── texto nativo (pdfminer)
def try_pdf_text(pdf_path: str, width_frac=0.40, height_frac=0.25) -> Optional[str]:
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTPage, LTTextContainer, LTTextLine
    pages = extract_pages(pdf_path, maxpages=1)
    page_layout = next((p for p in pages if isinstance(p, LTPage)), None)
    if not page_layout: return None
    W, H = page_layout.width, page_layout.height
    x_min, y_min = W*(1-width_frac), H*(1-height_frac)
    lines: List[Tuple[float,float,str]] = []
    def visit(c):
        if isinstance(c, LTTextContainer):
            for line in c:
                if isinstance(line, LTTextLine):
                    x0,y0,x1,y1 = line.bbox
                    if x1>=x_min and y1>=y_min:
                        t = line.get_text().strip()
                        if t: lines.append((y1,x0,t))
        if hasattr(c, "__iter__"):
            for ch in c: visit(ch)
    visit(page_layout)
    lines.sort(key=lambda t:(-t[0], t[1]))
    if not lines: return None
    for i,(_,__,raw) in enumerate(lines):
        n = normalize(raw)
        if "numero" in n and "asignado" in n:
            tail = raw.split(":",1)[1] if ":" in raw else ""
            candidate = (tail+" "+(lines[i+1][2] if i+1<len(lines) else "")).strip()
            m = PHONE_RE.search(candidate) or PHONE_RE.search(" ".join(l[2] for l in lines[i:]))
            if m: return m.group(0).strip()
    return None

# ───────────────────────── OCR esquina superior derecha
def ocr_top_right(pdf_path: str, width_frac=0.40, height_frac=0.25) -> Optional[str]:
    import fitz
    from PIL import Image, ImageOps, ImageFilter
    import pytesseract

    td = _resolve_tessdata_dir()
    cfg = '--psm 6 --oem 3' + (f' --tessdata-dir "{td}"' if td else '')

    doc = fitz.open(pdf_path)
    if len(doc)==0: return None
    page = doc[0]
    pm = page.get_pixmap(matrix=fitz.Matrix(2.0,2.0))
    img = Image.open(io.BytesIO(pm.tobytes("png")))

    W,H = img.size
    x0,y0 = int(W*(1-width_frac)), 0
    x1,y1 = W, int(H*height_frac)
    crop = img.crop((x0,y0,x1,y1))
    crop = crop.resize((int(crop.width*1.5), int(crop.height*1.5)), Image.LANCZOS)
    gray = ImageOps.grayscale(crop).filter(ImageFilter.UnsharpMask(radius=1.2, percent=150, threshold=3))

    data = pytesseract.image_to_data(gray, lang="spa+eng", config=cfg, output_type=pytesseract.Output.DICT)
    n = len(data.get("text", [])); lines={}
    for i in range(n):
        try: conf = int(data["conf"][i])
        except: conf = -1
        if conf<0: continue
        key = (data["page_num"][i], data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append((data.get("left",[0])[i], data["text"][i]))
    for k in lines: lines[k].sort(key=lambda t:t[0])
    keys = sorted(lines.keys())
    for idx,k in enumerate(keys):
        tokens = [t for _,t in lines[k] if t.strip()]
        if not tokens: continue
        raw_line = " ".join(tokens); nline = normalize(raw_line)
        if "numero" in nline and "asignado" in nline:
            tail = raw_line.split(":",1)[1] if ":" in raw_line else ""
            nxt  = keys[idx+1] if idx+1<len(keys) else None
            nxt_txt = " ".join([t for _,t in lines[nxt]]) if nxt else ""
            cand = (tail+" "+nxt_txt).strip()
            m = PHONE_RE.search(cand)
            if m: return m.group(0).strip()
    txt = pytesseract.image_to_string(gray, lang="spa+eng", config=cfg)
    pos = normalize(txt).find("numero asignado")
    if pos>=0:
        m = PHONE_RE.search(txt[pos:pos+500])
        if m: return m.group(0).strip()
    return None

def digits_only(s: str) -> str:
    return re.sub(r'\D','',s)

def copy_pdf_with_digits_name(src_pdf: str, phone: str) -> str:
    out_dir = os.path.dirname(os.path.abspath(src_pdf))
    digits  = digits_only(phone)
    if not digits: raise ValueError("El teléfono extraído no contiene dígitos.")
    dst = os.path.join(out_dir, f"{digits}.pdf")
    shutil.copyfile(src_pdf, dst)  # sobrescribe
    return dst

def main():
    if len(sys.argv)!=2:
        print("Uso: extrae_tel_pdf <archivo.pdf>", file=sys.stderr); sys.exit(2)
    pdf = sys.argv[1]
    if not (os.path.isfile(pdf) and pdf.lower().endswith(".pdf")):
        print("ERROR: Debe indicar un archivo .pdf existente.", file=sys.stderr); sys.exit(2)
    try:
        phone = try_pdf_text(pdf)
    except Exception:
        phone = None
    if not phone:
        try:
            phone = ocr_top_right(pdf)
        except Exception as e:
            print(f"ERROR OCR: {e}", file=sys.stderr); sys.exit(1)
    if not phone:
        print("ERROR: No se encontró 'Número asignado:' con teléfono en la esquina superior derecha.", file=sys.stderr)
        sys.exit(3)
    try:
        _ = copy_pdf_with_digits_name(pdf, phone)
    except Exception as e:
        print(f"ERROR al crear/reescribir la copia del PDF: {e}", file=sys.stderr)
        print(phone); sys.exit(4)
    print(phone); sys.exit(0)

if __name__ == "__main__":
    main()
