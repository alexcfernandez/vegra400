# -*- coding: utf-8 -*-
"""Orquestador: de la lista de piezas (revisada) a los 3 entregables."""
import os, math
from collections import OrderedDict
from engine import precios, despiece, materiales

COLS = ["grup", "codi", "descr", "w1", "h1", "w2", "h2", "uts", "unit", "preu"]

def _num(x, default=0):
    x = (x or "").strip().replace(",", ".")
    try: return float(x)
    except ValueError: return default

def parse_csv(text):
    groups = OrderedDict(); labor = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith("#"): continue
        parts = [c.strip() for c in s.split(";")]
        if parts[0].lower() == "grup": continue            # cabecera
        parts += [""] * (len(COLS) - len(parts))
        grup, codi, descr, w1, h1, w2, h2, uts, unit, preu = parts[:10]
        if codi == "treb":
            labor.append((descr, _num(preu))); continue
        item = (codi, descr, int(_num(w1)), int(_num(h1)), int(_num(w2)), int(_num(h2)),
                _num(uts), unit or "ut", (_num(preu) if preu.strip() else None))
        groups.setdefault(grup, []).append(item)
    return list(groups.items()), labor

def to_pieces(groups):
    pcs = []; n = 0
    for _titulo, items in groups:
        for (codi, descr, w1, h1, w2, h2, uts, unit, _preu) in items:
            n += 1
            if codi in ("rec", "red"):
                Lmm = max(1, int(round(uts * 1000)))
                ntr = max(1, math.ceil(Lmm / despiece.MAX_TRAMO))
                tl = int(round(Lmm / ntr))
                pcs.append(despiece.Pieza(f"P{n}", "conducte", w1, h1, L=tl,
                                          ext_a="M20", ext_b="M20", gauge=0.8, qty=ntr))
            elif codi == "tapa":
                pcs.append(despiece.Pieza(f"P{n}", "tapa", w1, h1, qty=max(1, int(round(uts)))))
    return pcs

def generate_all(csv_text, outdir):
    os.makedirs(outdir, exist_ok=True)
    groups, labor = parse_csv(csv_text)
    out = {}
    mats = materiales.compute(groups)
    out["presupuesto"] = precios.build_budget(groups, labor, os.path.join(outdir, "presupuesto_auto.xlsx"), materials=mats)
    pcs = to_pieces(groups)
    if pcs:
        out["dxf"] = despiece.build_cnc_dxf(pcs, os.path.join(outdir, "despiece_corte.dxf"))
        out["parte"] = despiece.build_shop_pdf(pcs, os.path.join(outdir, "parte_taller.pdf"))
        out["despiece_csv"] = despiece.parts_csv(pcs, os.path.join(outdir, "despiece.csv"))
    return out
