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
    UNITS = ("m", "ut", "ml", "u", "m.", "ut.")
    for ln in text.splitlines():
        s = ln.strip()
        if not s or s.startswith("#"): continue
        parts = [c.strip() for c in s.split(";")]
        if parts[0].lower() == "grup": continue
        if len(parts) < 4: continue
        grup, codi, descr = parts[0], parts[1], parts[2]
        rest = parts[3:]
        unit_idx = None
        for i, p in enumerate(rest):
            if p.strip().lower() in UNITS:
                unit_idx = i; break
        if unit_idx is not None and unit_idx >= 1:
            unit = rest[unit_idx].strip().lower().rstrip(".")
            uts = _num(rest[unit_idx - 1])
            dims = rest[:unit_idx - 1]
            preu = rest[unit_idx + 1] if len(rest) > unit_idx + 1 else ""
        else:
            rest += [""] * (7 - len(rest))
            dims = rest[:4]; uts = _num(rest[4]); unit = rest[5] or "ut"; preu = rest[6]
        w1 = int(_num(dims[0])) if len(dims) > 0 else 0
        h1 = int(_num(dims[1])) if len(dims) > 1 else 0
        w2 = int(_num(dims[2])) if len(dims) > 2 and dims[2] != "" else w1
        h2 = int(_num(dims[3])) if len(dims) > 3 and dims[3] != "" else h1
        if codi == "treb":
            labor.append((descr, _num(preu))); continue
        item = (codi, descr, w1, h1, w2, h2, uts, unit or "ut",
                (_num(preu) if str(preu).strip() else None))
        groups.setdefault(grup, []).append(item)
    return list(groups.items()), labor

def to_pieces(groups):
    pcs = []; n = 0
    for _titulo, items in groups:
        for (codi, descr, w1, h1, w2, h2, uts, unit, _preu) in items:
            n += 1
            if codi == "rec":
                Lmm = max(1, int(round(uts * 1000)))
                ntr = max(1, math.ceil(Lmm / despiece.MAX_TRAMO))
                tl = int(round(Lmm / ntr))
                pcs.append(despiece.Pieza(f"P{n}", "conducte", w1, h1, L=tl,
                                          ext_a="M20", ext_b="M20", gauge=0.8, qty=ntr))
            elif codi == "red":
                # CONO: longitud completa; el troceado a 1500 + interpolación
                # de la sección lo hace desarrollo_cono() dentro de despiece.py
                Lmm = max(1, int(round(uts * 1000))) if unit == "m" else max(1, int(round(uts)))
                pcs.append(despiece.Pieza(f"P{n}", "cono", w1, h1, L=Lmm,
                                          w2=w2, h2=h2, ext_a="M20", ext_b="M20",
                                          gauge=0.8, qty=1))
            elif codi == "tapa":
                pcs.append(despiece.Pieza(f"P{n}", "tapa", w1, h1, qty=max(1, int(round(uts)))))
            elif codi in ("c90", "c45"):
                ang = 90 if codi == "c90" else 45
                pcs.append(despiece.Pieza(f"P{n}", "curva", w1, h1, angle=ang,
                                          ext_a="M20", ext_b="M20", gauge=0.8,
                                          qty=max(1, int(round(uts)))))
            elif codi == "inj":
                pcs.append(despiece.Pieza(f"P{n}", "injert", w1, h1, L=despiece.INJERT_COLLAR,
                                          ext_a="M20", ext_b="M20", gauge=0.8,
                                          qty=max(1, int(round(uts)))))
    return pcs

def generate_all(csv_text, outdir, project=None, client=None):
    os.makedirs(outdir, exist_ok=True)
    groups, labor = parse_csv(csv_text)
    out = {}
    mats = materiales.compute(groups)
    out["presupuesto"] = precios.build_budget(groups, labor, os.path.join(outdir, "presupuesto_auto.xlsx"), materials=mats)
    pcs = to_pieces(groups)
    if pcs:
        out["dxf"] = despiece.build_cnc_dxf(pcs, os.path.join(outdir, "despiece_corte.dxf"))
        out["parte"] = despiece.build_shop_pdf(pcs, os.path.join(outdir, "parte_taller.pdf"), project=project, client=client)
        out["despiece_csv"] = despiece.parts_csv(pcs, os.path.join(outdir, "despiece.csv"))
    return out
