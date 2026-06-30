# -*- coding: utf-8 -*-
"""Extracción de datos del plano. Hoy: cotas del PDF por OCR (aproximado, para revisión).
Cuando llegue el DXF, aquí se añade el lector vectorial (cotas y conductos como objetos)."""
import re
import fitz
import pytesseract
from PIL import Image

CFG = '--psm 11 -c tessedit_char_whitelist=0123456789x'

def _ocr_vals(img):
    d = pytesseract.image_to_data(img, config=CFG, output_type=pytesseract.Output.DICT)
    out = []
    for i, tx in enumerate(d['text']):
        tx = tx.strip()
        if re.fullmatch(r'\d{2,5}', tx) and int(d['conf'][i]) >= 40:
            out.append(int(tx))
    return out

def extract_cotas(pdf_path, dpi=250):
    """Devuelve dict con cotas detectadas (valores únicos ordenados) y total de detecciones."""
    doc = fitz.open(pdf_path)
    page = doc[0]
    pix = page.get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L")
    vals = []
    vals += _ocr_vals(img)
    vals += _ocr_vals(img.transpose(Image.ROTATE_90))
    vals += _ocr_vals(img.transpose(Image.ROTATE_270))
    # también nº de trazos vectoriales (indicador de plano CAD)
    nlines = sum(1 for dr in page.get_drawings() for it in dr['items'] if it[0] == 'l')
    uniq = sorted(set(vals))
    return {"cotas": uniq, "n_detecciones": len(vals), "n_trazos": nlines}

def candidate_csv(cotas):
    """Plantilla de revisión pre-rellenada. Honesto: del PDF no se deduce la topología,
    así que dejamos cabecera + cotas detectadas como ayuda para que el técnico complete."""
    header = "grup;codi;descr;w1;h1;w2;h2;uts;unit;preu"
    ayuda = "# cotas detectadas en el plano (mm): " + ", ".join(str(c) for c in cotas if c >= 100)
    ejemplo = "1.1 INTERIOR A APORTACIO;rec;Conducte 800x150;800;150;800;150;90.84;m;"
    return "\n".join([header, ayuda, ejemplo])
