# -*- coding: utf-8 -*-
"""Lector de DXF en STREAMING (baja memoria): funciona con archivos de 80 MB+.
Extrae cotas (DIMENSION cod.42), capas de conductos/cotas y longitudes,
sin cargar todo el archivo en memoria. La reconstruccion pieza a pieza es el modulo siguiente."""
import math, re

COND_RX = re.compile(r"cond|conduct|clima|tub|aire|impuls|retorn|ventil", re.I)
COTA_RX = re.compile(r"cota|cote", re.I)

def _pairs(fh):
    while True:
        c = fh.readline()
        if c == "": return
        v = fh.readline()
        if v == "": return
        yield c.strip(), v.rstrip("\r\n")

def analyze(path, max_layers=25):
    ent = {}; lay = {}; dim_vals = []; duct_len = {}
    version = "?"; cur_type = None; cur_layer = "0"
    lx0 = ly0 = lx1 = ly1 = None; want_ver = False
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        for code, val in _pairs(fh):
            if code == "9":
                want_ver = (val == "$ACADVER"); continue
            if want_ver and code == "1":
                version = val; want_ver = False; continue
            if code == "0":
                if cur_type == "LINE" and None not in (lx0, ly0, lx1, ly1) and COND_RX.search(cur_layer or ""):
                    duct_len[cur_layer] = duct_len.get(cur_layer, 0) + math.dist((lx0, ly0), (lx1, ly1))
                cur_type = val; ent[val] = ent.get(val, 0) + 1
                cur_layer = "0"; lx0 = ly0 = lx1 = ly1 = None
            elif code == "8":
                cur_layer = val; lay[val] = lay.get(val, 0) + 1
            elif code == "42" and cur_type == "DIMENSION":
                try:
                    m = float(val)
                    if m > 1: dim_vals.append(round(m))
                except Exception:
                    pass
            elif cur_type == "LINE":
                try:
                    if code == "10": lx0 = float(val)
                    elif code == "20": ly0 = float(val)
                    elif code == "11": lx1 = float(val)
                    elif code == "21": ly1 = float(val)
                except Exception:
                    pass
    cotas = sorted({v for v in dim_vals if v >= 50})
    cond_layers = {k: lay[k] for k in lay if COND_RX.search(k)}
    for k, v in duct_len.items():
        cond_layers.setdefault(k, 0)
    cota_layers = {k: lay[k] for k in lay if COTA_RX.search(k)}
    top_layers = dict(sorted(lay.items(), key=lambda x: -x[1])[:max_layers])
    return {"version": version, "n_dim": len(dim_vals), "cotas": cotas,
            "cond_layers": cond_layers, "cota_layers": cota_layers,
            "duct_len_m": {k: round(v / 1000, 1) for k, v in duct_len.items()},
            "top_layers": top_layers,
            "entities": dict(sorted(ent.items(), key=lambda x: -x[1])[:10])}

def review_csv(a):
    cond = "; ".join("%s (%s el.)" % (k, v) for k, v in a["cond_layers"].items()) or "cap detectada pel nom"
    cotal = "; ".join("%s (%s)" % (k, v) for k, v in a["cota_layers"].items()) or "cap"
    cotas = ", ".join(str(c) for c in a["cotas"]) or "-"
    return "\n".join([
        "grup;codi;descr;w1;h1;w2;h2;uts;unit;preu",
        "# DXF llegit OK (%s) - %d cotes DIMENSION" % (a["version"], a["n_dim"]),
        "# Capes de CONDUCTES detectades: %s" % cond,
        "# Capes de COTES: %s" % cotal,
        "# Cotes (mm): %s" % cotas,
        "# (els noms de capa canvien segons el projecte; el muntatge automatic seccio+llargada es el modul seguent)",
    ])


def render_ducts_png(path, out_png, max_lines=8000):
    """Dibuixa NOMES les linies de les capes de conductes a una imatge PNG.
    Lectura en streaming (baixa memoria) per aguantar fitxers grans."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    segs = []
    cur_type = None; cur_layer = "0"; x0 = y0 = x1 = y1 = None
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        for code, val in _pairs(fh):
            if code == "0":
                if cur_type == "LINE" and None not in (x0, y0, x1, y1) and COND_RX.search(cur_layer or ""):
                    segs.append(((x0, x1), (y0, y1)))
                    if len(segs) >= max_lines:
                        break
                cur_type = val; cur_layer = "0"; x0 = y0 = x1 = y1 = None
            elif code == "8":
                cur_layer = val
            elif cur_type == "LINE":
                try:
                    if code == "10": x0 = float(val)
                    elif code == "20": y0 = float(val)
                    elif code == "11": x1 = float(val)
                    elif code == "21": y1 = float(val)
                except Exception:
                    pass
    if not segs:
        return None
    fig, ax = plt.subplots(figsize=(11, 8))
    for xs, ys in segs:
        ax.plot(xs, ys, color="black", linewidth=0.6)
    ax.set_aspect("equal"); ax.axis("off")
    fig.savefig(out_png, dpi=130, bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)
    return out_png
