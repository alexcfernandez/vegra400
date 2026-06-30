# -*- coding: utf-8 -*-
"""Lector de DXF: cotas reales (DIMENSION), capas de conducto y geometria.
Lectura en una sola pasada y defensiva, para no agotar memoria en DXF grandes.
La reconstruccion seccion+longitud por pieza es el modulo siguiente."""
import math, re
from collections import defaultdict

def _open(path):
    import ezdxf
    try:
        return ezdxf.readfile(path)              # ligero
    except Exception:
        from ezdxf import recover
        doc, _ = recover.readfile(path)          # robusto (mas memoria)
        return doc

def analyze(path):
    doc = _open(path)
    msp = doc.modelspace()
    dim_vals = []
    duct_len = defaultdict(float)
    duct_n = defaultdict(int)
    blocks = defaultdict(int)
    rx = re.compile(r"COND|Cono", re.I)
    for e in msp:                                # UNA sola pasada
        t = e.dxftype()
        if t == "DIMENSION":
            try:
                m = e.get_measurement()
                if isinstance(m, (int, float)) and m > 1:
                    dim_vals.append(round(m))
            except Exception:
                pass
        elif t == "LINE":
            lyr = e.dxf.layer
            if rx.search(lyr):
                try:
                    s, q = e.dxf.start, e.dxf.end
                    duct_len[lyr] += math.dist((s.x, s.y), (q.x, q.y))
                    duct_n[lyr] += 1
                except Exception:
                    pass
        elif t == "INSERT":
            blocks[e.dxf.name] += 1
    cotas = sorted({v for v in dim_vals if v >= 50})
    duct_layers = {k: {"lines": duct_n[k], "length_m": round(v / 1000, 1)}
                   for k, v in duct_len.items() if duct_n[k]}
    top_blocks = dict(sorted(blocks.items(), key=lambda x: -x[1])[:10])
    return {"version": str(doc.acad_release), "n_dim": len(dim_vals),
            "cotas": cotas, "duct_layers": duct_layers, "blocks": top_blocks}

def review_csv(a):
    """Pre-omple la revisio amb les dades REALS del DXF + scaffold buit per completar.
    No inventa peces: nomes mostra el que s'ha llegit."""
    cotas = ", ".join(str(c) for c in a["cotas"])
    capas = "; ".join("%s (%s m)" % (k, v["length_m"]) for k, v in a["duct_layers"].items()) or "cap"
    return "\n".join([
        "grup;codi;descr;w1;h1;w2;h2;uts;unit;preu",
        "# DXF llegit OK - %d cotes reals" % a["n_dim"],
        "# Capes de conducte: %s" % capas,
        "# Cotes (mm): %s" % cotas,
        "# (el muntatge automatic seccio+llargada per peca es el modul seguent;",
        "#  de moment completa les files amb el format de dalt)",
    ])
