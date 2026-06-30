# -*- coding: utf-8 -*-
"""Lector de DXF del arquitecto. Extrae datos REALES (no OCR):
cotas (DIMENSION), capas de conducto y geometría, bloques (toberas/gàbies).
La reconstrucción sección+longitud por pieza es el módulo siguiente (calibrado con el presupuesto)."""
import math, re
from collections import Counter
import ezdxf
from ezdxf import recover

def _len(e):
    s, t = e.dxf.start, e.dxf.end
    return math.dist((s.x, s.y), (t.x, t.y))

def analyze(path):
    doc, _ = recover.readfile(path)
    msp = doc.modelspace()
    dims = []
    for e in msp.query("DIMENSION"):
        try:
            m = e.get_measurement()
            if isinstance(m, (int, float)) and m > 1:
                p = e.dxf.defpoint
                dims.append((round(m), round(p.x), round(p.y)))
        except Exception:
            pass
    cotas = sorted({v for v, _, _ in dims if v >= 50})
    # capas de conducto (nombre contiene COND o Cono)
    duct = {}
    for lyr in {e.dxf.layer for e in msp}:
        if re.search(r"COND|Cono", lyr, re.I):
            lines = msp.query(f'LINE[layer=="{lyr}"]')
            n = len(lines)
            if n:
                duct[lyr] = {"lines": n, "length_m": round(sum(_len(x) for x in lines) / 1000, 1)}
    blocks = Counter(e.dxf.name for e in msp.query("INSERT"))
    return {"version": str(doc.acad_release), "n_dim": len(dims),
            "cotas": cotas, "dims": dims, "duct_layers": duct,
            "blocks": dict(blocks.most_common(10))}

def review_csv(a):
    """Pre-rellena la revisión con los datos REALES del DXF + scaffold para completar."""
    cotas = ", ".join(str(c) for c in a["cotas"])
    capas = "; ".join(f"{k} ({v['length_m']} m)" for k, v in a["duct_layers"].items())
    head = "grup;codi;descr;w1;h1;w2;h2;uts;unit;preu"
    lines = [
        head,
        f"# DXF llegit OK · {a['n_dim']} cotes reals",
        f"# Capes de conducte detectades: {capas}",
        f"# Cotes (mm): {cotas}",
        "# (la reconstrucció automàtica secció+llargada per peça és el mòdul següent; de moment completa/edita les files)",
        "1.1 INTERIOR - B EXTRACCIO;rec;Conducte 800x150;800;150;800;150;90.84;m;",
    ]
    return "\n".join(lines)
