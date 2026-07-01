# -*- coding: utf-8 -*-
"""Lector de DXF del arquitecto. v1:
   - Con ezdxf (archivos de tamaño normal): filtra las capas de CONDUCTO, separa por
     sistema (IMP / RET / INVFLUX), lee las cotas DIMENSION como objetos (valor real)
     y asigna cada cota a su sistema por cercanía a la geometría de ese sistema.
   - Fallback en STREAMING (baja memoria) para archivos muy grandes.
   La reconstrucción pieza a pieza (cada fitting con su sección) es el módulo siguiente;
   esto entrega ya los DATOS REALES (secciones, largos, trams de 1500) por sistema."""
import math, re, os

COND_RX = re.compile(r"cond|conduct|clima|tub|aire|impuls|retorn|ventil|panell|planxa|meto", re.I)
COTA_RX = re.compile(r"cota|cote", re.I)
SIZE_LIMIT_MB = 40   # por encima de esto, modo streaming (no cargar todo en memoria)

def _system(layer):
    L = (layer or "").lower()
    if "invflux" in L: return "INVFLUX"
    if "cond" in L and "imp" in L: return "IMP"
    if "cond" in L and ("ret" in L or "retorn" in L): return "RET"
    if "condensat" in L or "retorn" in L: return "RET"
    if "imp" in L: return "IMP"
    if "ret" in L: return "RET"
    return None

def _is_plan(layer):
    L = (layer or "").lower()
    return ("top" in L) or ("plan" in L) or not any(
        v in L for v in ("front", "left", "right", "back", "iso ", "iso-", "isosw", "isonw"))

# ----------------------- LECTOR RICO (ezdxf) -----------------------
def _measure_heights(segs):
    """segs: lineas (x0,y0,x1,y1) de una vista de ALZADO. Mide los gaps verticales
       entre lineas horizontales = ALTURAS de seccion."""
    H = []; seen = set()
    for x0, y0, x1, y1 in segs:
        k = (round(x0), round(y0), round(x1), round(y1))
        if k in seen: continue
        seen.add(k)
        if abs(y1 - y0) < 2 and abs(x1 - x0) > 30:
            H.append((min(x0, x1), max(x0, x1), round((y0 + y1) / 2)))
    H.sort(key=lambda s: s[2]); hs = []
    for i in range(len(H)):
        a0, a1, ac = H[i]
        for j in range(i + 1, len(H)):
            b0, b1, bc = H[j]
            if bc - ac > 2000: break
            ov = min(a1, b1) - max(a0, b0)
            if ov > 100 and 80 < (bc - ac) < 2000:
                mid = any(ac < H[k][2] < bc and min(a1, H[k][1]) - max(a0, H[k][0]) > 100
                          for k in range(len(H)) if k != i and k != j)
                if not mid:
                    hs.append(int(round((bc - ac) / 5) * 5)); break
    return hs


def _measure_runs(segs):
    """segs: lista de (x0,y0,x1,y1) en PLANTA de un sistema. Empareja paredes
       paralelas contiguas (sin otra pared en medio) -> tram = (ample, llarg)."""
    H = []; V = []; seen = set()
    for x0, y0, x1, y1 in segs:
        k = (round(x0), round(y0), round(x1), round(y1))
        if k in seen: continue
        seen.add(k)
        if abs(y1 - y0) < 2 and abs(x1 - x0) > 50:
            H.append((min(x0, x1), max(x0, x1), round((y0 + y1) / 2)))
        elif abs(x1 - x0) < 2 and abs(y1 - y0) > 50:
            V.append((min(y0, y1), max(y0, y1), round((x0 + x1) / 2)))
    runs = []
    for grp in (H, V):
        grp = sorted(grp, key=lambda s: s[2])
        for i in range(len(grp)):
            a0, a1, ac = grp[i]
            for j in range(i + 1, len(grp)):
                b0, b1, bc = grp[j]
                if bc - ac > 2600: break
                ov = min(a1, b1) - max(a0, b0)
                if ov > 150 and 80 < (bc - ac) < 2600:
                    mid = any(ac < grp[k][2] < bc and
                              min(a1, grp[k][1]) - max(a0, grp[k][0]) > 150
                              for k in range(len(grp)) if k != i and k != j)
                    if not mid:
                        runs.append((int(round(bc - ac)), int(round(ov))))
                        break
    return runs


def _analyze_ezdxf(path):
    import ezdxf
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    dims = []                      # (valor, x, y)
    duct_lines = {}                # sistema -> [(mx,my,length,is_plan)]
    plan_segs = {}                 # sistema -> [(x0,y0,x1,y1)] solo planta
    elev_segs = {}                 # sistema -> [(x0,y0,x1,y1)] solo alzados (front/left)
    cond_layers = {}
    for e in msp:
        t = e.dxftype()
        lyr = e.dxf.layer
        if t == "DIMENSION":
            try:
                m = e.get_measurement()
                if isinstance(m, (int, float)) and m > 1:
                    try:
                        p = e.dxf.defpoint
                        x, y = float(p.x), float(p.y)
                    except Exception:
                        x = y = 0.0
                    dims.append((int(round(m)), x, y))
            except Exception:
                pass
            continue
        s = _system(lyr)
        if s and t == "LINE":
            cond_layers[lyr] = cond_layers.get(lyr, 0) + 1
            a, b = e.dxf.start, e.dxf.end
            mx, my = (a.x + b.x) / 2.0, (a.y + b.y) / 2.0
            isp = _is_plan(lyr)
            duct_lines.setdefault(s, []).append((mx, my, math.dist((a.x, a.y), (b.x, b.y)), isp))
            if isp:
                plan_segs.setdefault(s, []).append((a.x, a.y, b.x, b.y))
            elif "front" in lyr.lower() or "left" in lyr.lower():
                elev_segs.setdefault(s, []).append((a.x, a.y, b.x, b.y))

    # asignar cada cota al sistema cuya geometría tiene más cerca
    cotas_by_sys = {}
    allvals = []
    for v, x, y in dims:
        allvals.append(v)
        best, bd = None, 1e30
        for s, lines in duct_lines.items():
            for mx, my, _l, _p in lines:
                d = (mx - x) ** 2 + (my - y) ** 2
                if d < bd:
                    bd, best = d, s
        if best:
            cotas_by_sys.setdefault(best, []).append(v)

    cotas = sorted(set(v for v in allvals if v >= 50))
    cotas_by_system = {s: sorted(set(vs)) for s, vs in cotas_by_sys.items()}
    duct_len_m = {}
    for s, lines in duct_lines.items():
        plan = sum(l for _mx, _my, l, p in lines if p)
        duct_len_m[s] = round(plan / 1000.0, 1)
    n1500 = sum(1 for v in allvals if v == 1500)
    # medir tramos (ancho x largo) por sistema, filtrando ruido (un tram real es
    # mas largo que ancho, no excesivamente ancho, y de cierta longitud)
    runs_by_system = {}
    for s, segs in plan_segs.items():
        runs = _measure_runs(segs)
        clean = sorted({(round(w / 5) * 5, l) for w, l in runs
                        if l >= 400 and w <= 1200 and l >= 0.8 * w}, key=lambda t: -t[1])
        if clean:
            runs_by_system[s] = clean[:25]
    # ALTURAS de seccion leidas en los alzados, por sistema
    heights_by_system = {}
    for s, segs in elev_segs.items():
        hs = [h for h in _measure_heights(segs) if 50 <= h <= 1600]
        if hs:
            from collections import Counter as _C
            heights_by_system[s] = [h for h, _n in _C(hs).most_common(10)]
    return {"version": doc.dxfversion, "engine": "ezdxf", "n_dim": len(dims),
            "cotas": cotas, "cotas_by_system": cotas_by_system,
            "cond_layers": cond_layers, "duct_len_m": duct_len_m,
            "runs_by_system": runs_by_system, "heights_by_system": heights_by_system,
            "n_trams_1500": n1500}

# ----------------------- FALLBACK STREAMING (archivos enormes) -----------------------
def _pairs(fh):
    while True:
        c = fh.readline()
        if c == "": return
        v = fh.readline()
        if v == "": return
        yield c.strip(), v.rstrip("\r\n")

def _analyze_streaming(path, max_layers=25):
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
    duct_len_m = {k: round(v / 1000, 1) for k, v in duct_len.items()}
    # agrupar largos por sistema
    by_sys = {}
    for k, v in duct_len_m.items():
        s = _system(k)
        if s: by_sys[s] = round(by_sys.get(s, 0) + v, 1)
    return {"version": version, "engine": "streaming", "n_dim": len(dim_vals),
            "cotas": cotas, "cotas_by_system": {}, "cond_layers": cond_layers,
            "duct_len_m": by_sys or duct_len_m, "n_trams_1500": dim_vals.count(1500)}

def analyze(path):
    try:
        if os.path.getsize(path) <= SIZE_LIMIT_MB * 1024 * 1024:
            return _analyze_ezdxf(path)
    except Exception:
        pass
    return _analyze_streaming(path)

# ----------------------- RENDER de conductos (PNG limpio) -----------------------
def render_ducts_png(path, out_png, max_lines=20000):
    """Dibuja SOLO las líneas de las capas de conducto a un PNG (vistas en planta),
       en streaming (baja memoria). Da un dibujo limpio de la red, sin el edificio."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    segs = []
    cur_type = None; cur_layer = "0"; x0 = y0 = x1 = y1 = None
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        for code, val in _pairs(fh):
            if code == "0":
                if (cur_type == "LINE" and None not in (x0, y0, x1, y1)
                        and COND_RX.search(cur_layer or "") and _is_plan(cur_layer)):
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
    fig.savefig(out_png, dpi=140, bbox_inches="tight", pad_inches=0.1)
    plt.close(fig)
    return out_png
