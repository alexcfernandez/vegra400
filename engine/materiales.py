# -*- coding: utf-8 -*-
"""Ingeniería inversa de materiales y accesorios a partir del despiece.
Calcula m² de chapa, peso, abrazaderas, juntas metu y tornillos.
Ratios editables (en la hoja Materials del Excel)."""
import math

SEAM_M = 0.045  # costura Pittsburgh añade ~45 mm al perímetro desarrollado
TAPA_LIP = 25
MAX_TRAMO = 1500

def _perim_mm(w1, h1, w2, h2):
    if w2 and h2:
        return (2 * (w1 + h1) + 2 * (w2 + h2)) / 2
    return 2 * (w1 + h1)

def compute(groups):
    area = 0.0          # m² netos de chapa
    metres = 0.0        # metros lineales de conducto
    peces = 0           # nº de piezas (tramos + accesorios + tapes)
    brides_mm = 0.0     # perímetro total de bridas (para estimar tornillos)
    for _titulo, items in groups:
        for (codi, descr, w1, h1, w2, h2, uts, unit, _preu) in items:
            p_mm = _perim_mm(w1, h1, w2, h2)
            p_m = p_mm / 1000.0
            if codi in ("rec", "red"):
                n = max(1, math.ceil(uts * 1000 / MAX_TRAMO))
                area += (p_m + SEAM_M) * uts
                metres += uts
                peces += n
                brides_mm += n * 2 * p_mm
            elif codi == "tapa":
                q = max(1, int(round(uts)))
                area += ((w1 + 2 * TAPA_LIP) * (h1 + 2 * TAPA_LIP)) / 1e6 * q
                peces += q
                brides_mm += q * p_mm
            elif codi in ("c90", "c45", "inj", "des", "tmalla"):
                q = max(1, int(round(uts)))
                area += (p_m + SEAM_M) * 0.45 * q       # aprox. accesorio
                peces += q
                brides_mm += q * 2 * p_mm
            # esp: material a parte (entrada manual)
    return {"area_neta_m2": round(area, 1), "metres": round(metres, 1),
            "peces": peces, "brides_mm": round(brides_mm)}
