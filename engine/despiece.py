#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DESPIECE AUTOMÁTICO DE CONDUCTES — v0.2
Tipos soportados: conducte recto, CONO (reducció), tapa.
Genera: (1) lista de despiece (CSV + consola), (2) DXF de corte para CNC,
        (3) parte de taller en PDF con cotas e isométrico.
NOVEDAD v0.2: las reduccions se desarrollan como CONO real (blank trapezoidal,
              pliegues que abanican, troceado interpolando la sección).
"""
import math, csv, datetime
import numpy as np
import ezdxf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

# ----------------------- REGLAS / PARÁMETROS -----------------------
MAX_TRAMO   = 1500
PITTS_BOLSA = 35
PITTS_PEST  = 10
SEAM        = PITTS_BOLSA + PITTS_PEST   # = 45 mm añadidos por 1 costura
N_COSTURES  = 1
METU_DEDUCT = 0
PAO_MARGIN  = 0
TAPA_PEST   = 25

# --- CURVAS / INJERTS (parámetros AJUSTABLES - pendientes de validar con Joan) ---
CURVA_THROAT_FACTOR = 0.5   # radio de garganta interior = factor * (dim. en el plano de giro)
                            #   0.5 -> radio centro = 1x el ancho (radio "largo"). Ajustable.
CURVA_SEAM   = SEAM         # costura añadida a las tiras de garganta/talón
INJERT_COLLAR = 250         # mm de largo por defecto del collar de un injert (stub)

# Largo de una reducció/cono cuando la lista NO trae longitud (pieza suelta "ut"):
CONO_TAPER  = 2.0           # largo ≈ TAPER * mayor cambio de dimensión (pendiente ~1:4 por lado)
CONO_MIN_LEN = 300          # mm, largo mínimo de una transición

PROYECTO = "(projecte)"
CLIENTE  = "(client)"
FECHA    = datetime.date.today().strftime("%d/%m/%Y")

# ----------------------- MODELO DE DATOS -----------------------
class Pieza:
    def __init__(self, ref, tipo, w, h, L=None, w2=None, h2=None,
                 ext_a="M20", ext_b="M20", gauge=0.8, qty=1,
                 material="Xapa simple galva", angle=90):
        self.ref, self.tipo = ref, tipo
        self.w, self.h, self.L = w, h, L
        self.w2 = w2 if w2 is not None else w     # sección de salida (cono)
        self.h2 = h2 if h2 is not None else h
        self.ext_a, self.ext_b = ext_a, ext_b
        self.gauge, self.qty, self.material = gauge, qty, material
        self.angle = angle                        # grados (curva)
        self.len_aprox = False                    # True si el largo es estimado (no venía en la lista)

    @property
    def descr(self):
        if self.tipo == "tapa":
            return f"Tapa {self.w}x{self.h} {self.ext_a}"
        if self.tipo == "cono":
            return (f"Reducció {self.w}x{self.h} a {self.w2}x{self.h2} - "
                    f"{self.L}L {self.ext_a}/{self.ext_b}")
        if self.tipo == "curva":
            return f"Curva {self.angle}° {self.w}x{self.h} {self.ext_a}/{self.ext_b}"
        if self.tipo == "injert":
            return f"Injert (collar) {self.w}x{self.h} - {self.L}L {self.ext_a}"
        return f"{self.tipo.capitalize()} {self.w}x{self.h} - {self.L}L {self.ext_a}/{self.ext_b}"

# ----------------------- LÓGICA DE FABRICACIÓN -----------------------
def trocear(L):
    n = max(1, math.ceil(L / MAX_TRAMO))
    base = round(L / n)
    segs = [base] * (n - 1) + [L - base * (n - 1)]
    return segs

def desarrollo_cuerpo(p):
    """Blanks de chapa plana para un conducte RECTO (sección constante)."""
    girth = 2 * (p.w + p.h) + N_COSTURES * SEAM
    segs = trocear(p.L)
    blanks = []
    for i, seg in enumerate(segs):
        a = p.ext_a if i == 0 else "M20"
        b = p.ext_b if i == len(segs) - 1 else "M20"
        length = seg
        if a == "M20": length -= METU_DEDUCT
        if b == "M20": length -= METU_DEDUCT
        if a == "PAO": length += PAO_MARGIN
        if b == "PAO": length += PAO_MARGIN
        etiqueta = p.descr + (f"  [tramo {i+1}/{len(segs)}]" if len(segs) > 1 else "")
        blanks.append(dict(tipo="recto", girth=girth, length=length, w=p.w, h=p.h,
                           a=a, b=b, ref=p.ref, etiqueta=etiqueta,
                           gauge=p.gauge, seg_nominal=seg))
    return blanks

def desarrollo_cono(p):
    """Blanks de chapa plana para una REDUCCIÓ (cono).
       Trocea la longitud a <=1500 e INTERPOLA la sección en cada corte:
       cada tramo es un sub-cono con su sección de entrada y de salida.
       El blank es un TRAPECIO (girth mayor en el extremo grande)."""
    w1, h1 = p.w, p.h
    w2, h2 = p.w2, p.h2
    L = max(1, int(p.L))
    segs = trocear(L)
    blanks = []
    cum = 0
    for i, seg in enumerate(segs):
        fa = cum / L
        fb = (cum + seg) / L
        wa = w1 + (w2 - w1) * fa; wb = w1 + (w2 - w1) * fb
        ha = h1 + (h2 - h1) * fa; hb = h1 + (h2 - h1) * fb
        ga = 2 * (wa + ha) + N_COSTURES * SEAM
        gb = 2 * (wb + hb) + N_COSTURES * SEAM
        a = p.ext_a if i == 0 else "M20"
        b = p.ext_b if i == len(segs) - 1 else "M20"
        etiqueta = p.descr + (f"  [tramo {i+1}/{len(segs)}]" if len(segs) > 1 else "")
        blanks.append(dict(tipo="cono", length=seg, seg_nominal=seg,
                           wa=round(wa), ha=round(ha), wb=round(wb), hb=round(hb),
                           ga=round(ga), gb=round(gb), a=a, b=b, ref=p.ref,
                           etiqueta=etiqueta, gauge=p.gauge, len_aprox=getattr(p, "len_aprox", False),
                           w=round((wa + wb) / 2), h=round((ha + hb) / 2)))
        cum += seg
    return blanks

def desarrollo_tapa(p):
    bw = p.w + 2 * TAPA_PEST
    bh = p.h + 2 * TAPA_PEST
    return [dict(tipo="tapa", w=p.w, h=p.h, bw=bw, bh=bh, pest=TAPA_PEST,
                 ref=p.ref, etiqueta=p.descr, gauge=p.gauge, a=p.ext_a, b="-")]

def _curva_geom(p):
    """Geometría de un codo rectangular WxH que gira p.angle grados.
       Gira en el plano de W (ancho). Mejillas = sectores de corona; garganta/talón = tiras."""
    W, H = p.w, p.h
    theta = math.radians(p.angle)
    ri = max(1.0, CURVA_THROAT_FACTOR * W)   # radio garganta (interior)
    ro = ri + W                              # radio talón (exterior)
    arc_in = ri * theta                      # largo desarrollado tira garganta
    arc_out = ro * theta                     # largo desarrollado tira talón
    depth = H + N_COSTURES * CURVA_SEAM      # ancho tira (con costura)
    return dict(W=W, H=H, ang=p.angle, theta=theta, ri=ri, ro=ro,
                arc_in=round(arc_in), arc_out=round(arc_out), depth=round(depth))

def desarrollo_curva(p):
    g = _curva_geom(p)
    g.update(tipo="curva", ref=p.ref, etiqueta=p.descr, gauge=p.gauge,
             a=p.ext_a, b=p.ext_b, w=p.w, h=p.h, length=g["ro"], seg_nominal=g["ro"])
    return [g]

def _annular_pts(cx, cy, ri, ro, theta, n=28):
    pts = []
    for i in range(n + 1):
        a = theta * i / n; pts.append((cx + ri*math.cos(a), cy + ri*math.sin(a)))
    for i in range(n + 1):
        a = theta * (n - i) / n; pts.append((cx + ro*math.cos(a), cy + ro*math.sin(a)))
    return pts

def desarrollar(p):
    if p.tipo == "tapa":  return desarrollo_tapa(p)
    if p.tipo == "cono":  return desarrollo_cono(p)
    if p.tipo == "curva": return desarrollo_curva(p)
    return desarrollo_cuerpo(p)   # conducte recto e injert (collar)

# fold lines (posiciones de pliegue) de un cono en un extremo dado
def _cono_fold_positions(w, h):
    x0 = PITTS_BOLSA
    x1 = x0 + w        # fin panel inferior
    x2 = x1 + h        # fin lateral 1
    x3 = x2 + w        # fin panel superior
    x4 = x3 + h        # fin lateral 2 (= girth - pest)
    return [x0, x1, x2, x3, x4]

# ----------------------- SALIDA: DXF DE CORTE -----------------------
def export_dxf(piezas, path):
    doc = ezdxf.new(setup=True)
    doc.units = ezdxf.units.MM
    msp = doc.modelspace()
    for lyr, col in [("CORTE", 1), ("PLEGADO", 5), ("TEXTO", 7), ("COTA_INFO", 3)]:
        if lyr not in doc.layers:
            doc.layers.add(lyr, color=col)
    doc.layers.get("PLEGADO").dxf.linetype = "DASHED"

    x0, y0, gap = 0.0, 0.0, 60.0
    rowmax = 0.0
    for p in piezas:
        for blank in desarrollar(p):
            for _copy in range(p.qty):
                if blank["tipo"] == "tapa":
                    _draw_tapa(msp, x0, y0, blank)
                    used_w, used_h = blank["bw"], blank["bh"]
                elif blank["tipo"] == "cono":
                    _draw_cono(msp, x0, y0, blank)
                    used_w, used_h = max(blank["ga"], blank["gb"]), blank["length"]
                elif blank["tipo"] == "curva":
                    used_w, used_h = _draw_curva(msp, x0, y0, blank)
                else:
                    _draw_recto(msp, x0, y0, blank)
                    used_w, used_h = blank["girth"], blank["length"]
                msp.add_text(blank["etiqueta"], height=12,
                             dxfattribs={"layer": "TEXTO"}).set_placement((x0, y0 - 18))
                x0 += used_w + gap
                rowmax = max(rowmax, used_h)
                if x0 > 6000:
                    x0 = 0.0; y0 += rowmax + gap + 30; rowmax = 0.0
    doc.saveas(path)

def _draw_recto(msp, x, y, b):
    g, L = b["girth"], b["length"]
    msp.add_lwpolyline([(x,y),(x+g,y),(x+g,y+L),(x,y+L)], close=True,
                       dxfattribs={"layer":"CORTE"})
    p1 = x + PITTS_BOLSA + b["w"]
    p2 = p1 + b["h"]
    p3 = p2 + b["w"]
    for fx in (p1, p2, p3):
        msp.add_line((fx,y),(fx,y+L), dxfattribs={"layer":"PLEGADO"})
    msp.add_line((x+PITTS_BOLSA,y),(x+PITTS_BOLSA,y+L), dxfattribs={"layer":"COTA_INFO"})
    msp.add_line((x+g-PITTS_PEST,y),(x+g-PITTS_PEST,y+L), dxfattribs={"layer":"COTA_INFO"})

def _draw_cono(msp, x, y, b):
    """Blank trapezoidal: extremo inferior (y) = girth ga; extremo superior (y+L) = girth gb.
       Pliegues que abanican (rectas que unen la posición en A con la posición en B)."""
    ga, gb, L = b["ga"], b["gb"], b["length"]
    # contorno (trapecio rectángulo: lado izquierdo recto en x, lado derecho inclinado)
    msp.add_lwpolyline([(x,y),(x+ga,y),(x+gb,y+L),(x,y+L)], close=True,
                       dxfattribs={"layer":"CORTE"})
    fa = _cono_fold_positions(b["wa"], b["ha"])   # extremo grande
    fb = _cono_fold_positions(b["wb"], b["hb"])   # extremo pequeño
    # pliegues internos (x1..x3): líneas inclinadas de A a B
    for k in (1, 2, 3):
        msp.add_line((x+fa[k], y), (x+fb[k], y+L), dxfattribs={"layer":"PLEGADO"})
    # marcas pittsburgh: bolsa (vertical, x=35) y pestaña (inclinada, girth-10)
    msp.add_line((x+PITTS_BOLSA, y), (x+PITTS_BOLSA, y+L), dxfattribs={"layer":"COTA_INFO"})
    msp.add_line((x+ga-PITTS_PEST, y), (x+gb-PITTS_PEST, y+L), dxfattribs={"layer":"COTA_INFO"})

def _draw_curva(msp, x, y, b):
    """Tila las 4 piezas del codo en el DXF: 2 mejillas (sector de corona) + garganta + talón.
       Devuelve (ancho_usado, alto_usado)."""
    gap = 40.0
    ri, ro, th = b["ri"], b["ro"], b["theta"]
    depth, arc_in, arc_out = b["depth"], b["arc_in"], b["arc_out"]
    cx = x; cy = y
    # 2 mejillas (idénticas), una al lado de otra
    cheek_w = ro
    for k in range(2):
        ox = x + k * (cheek_w + gap)
        pts = _annular_pts(ox, y, ri, ro, th)
        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "CORTE"})
        # radios extremos (líneas de cierre = bordes de unión con garganta/talón)
        msp.add_line((ox + ri, y), (ox + ro, y), dxfattribs={"layer": "COTA_INFO"})
        msp.add_line((ox + ri*math.cos(th), y + ri*math.sin(th)),
                     (ox + ro*math.cos(th), y + ro*math.sin(th)), dxfattribs={"layer": "COTA_INFO"})
    xstrip = x + 2 * (cheek_w + gap)
    # garganta (interior): rectángulo depth x arc_in
    msp.add_lwpolyline([(xstrip, y), (xstrip + arc_in, y),
                        (xstrip + arc_in, y + depth), (xstrip, y + depth)],
                       close=True, dxfattribs={"layer": "CORTE"})
    # talón (exterior): rectángulo depth x arc_out
    xstrip2 = xstrip + arc_in + gap
    msp.add_lwpolyline([(xstrip2, y), (xstrip2 + arc_out, y),
                        (xstrip2 + arc_out, y + depth), (xstrip2, y + depth)],
                       close=True, dxfattribs={"layer": "CORTE"})
    used_w = (xstrip2 + arc_out) - x
    used_h = max(ro, depth)
    return used_w, used_h

def _draw_tapa(msp, x, y, b):
    bw, bh, pe = b["bw"], b["bh"], b["pest"]
    pts = [(x+pe,y),(x+bw-pe,y),(x+bw-pe,y+pe),(x+bw,y+pe),(x+bw,y+bh-pe),
           (x+bw-pe,y+bh-pe),(x+bw-pe,y+bh),(x+pe,y+bh),(x+pe,y+bh-pe),
           (x,y+bh-pe),(x,y+pe),(x+pe,y+pe)]
    msp.add_lwpolyline(pts, close=True, dxfattribs={"layer":"CORTE"})
    msp.add_lwpolyline([(x+pe,y+pe),(x+bw-pe,y+pe),(x+bw-pe,y+bh-pe),(x+pe,y+bh-pe)],
                       close=True, dxfattribs={"layer":"PLEGADO"})

# ----------------------- SALIDA: PARTE DE TALLER (PDF) -----------------------
def _dim_h(ax, x1, x2, y, txt, off=0):
    ax.annotate("", (x1,y),(x2,y), arrowprops=dict(arrowstyle="<->", color="#222", lw=0.8))
    ax.text((x1+x2)/2, y+off+6, txt, ha="center", va="bottom", fontsize=7.5)

def _dim_v(ax, y1, y2, x, txt):
    ax.annotate("", (x,y1),(x,y2), arrowprops=dict(arrowstyle="<->", color="#222", lw=0.8))
    ax.text(x-8,(y1+y2)/2, txt, ha="right", va="center", rotation=90, fontsize=7.5)

def _iso(ax, w, h, L, ea, eb):
    c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
    def proj(x,y,z): return ((x-y)*c, z+(x+y)*s)
    P = {k: proj(*v) for k,v in {
        "A":(0,0,0),"B":(L,0,0),"C":(L,w,0),"D":(0,w,0),
        "E":(0,0,h),"F":(L,0,h),"G":(L,w,h),"H":(0,w,h)}.items()}
    edges=[("A","B"),("B","C"),("C","D"),("D","A"),("E","F"),("F","G"),
           ("G","H"),("H","E"),("A","E"),("B","F"),("C","G"),("D","H")]
    for a,b in edges:
        ax.plot([P[a][0],P[b][0]],[P[a][1],P[b][1]],color="#1a1a1a",lw=1.1)
    ax.text(*np.add(P["A"],(-3,-3)), ea, ha="right", va="top", fontsize=8, color="#b00")
    ax.text(*np.add(P["B"],(3,-3)),  eb, ha="left",  va="top", fontsize=8, color="#b00")
    ax.text(*np.add(np.divide(np.add(P["A"],P["B"]),2),(0,-14)), f"L={L}", ha="center", fontsize=7.5)
    ax.text(*np.add(np.divide(np.add(P["A"],P["E"]),2),(-12,0)), f"H={h}", ha="right", va="center", fontsize=7.5)
    ax.text(*np.add(np.divide(np.add(P["A"],P["D"]),2),(-6,4)), f"W={w}", ha="center", fontsize=7.5)
    ax.set_aspect("equal"); ax.axis("off")

def _iso_cono(ax, w1, h1, w2, h2, L, ea, eb):
    """Isométrico de un cono: cara cercana w1xh1, cara lejana w2xh2 (base alineada)."""
    c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
    def proj(x,y,z): return ((x-y)*c, z+(x+y)*s)
    near = {"P0":(0,0,0),"P1":(0,w1,0),"P2":(0,w1,h1),"P3":(0,0,h1)}
    far  = {"Q0":(L,0,0),"Q1":(L,w2,0),"Q2":(L,w2,h2),"Q3":(L,0,h2)}
    P = {k: proj(*v) for k,v in {**near, **far}.items()}
    edges = [("P0","P1"),("P1","P2"),("P2","P3"),("P3","P0"),
             ("Q0","Q1"),("Q1","Q2"),("Q2","Q3"),("Q3","Q0"),
             ("P0","Q0"),("P1","Q1"),("P2","Q2"),("P3","Q3")]
    for a,b in edges:
        ax.plot([P[a][0],P[b][0]],[P[a][1],P[b][1]],color="#1a1a1a",lw=1.1)
    ax.text(*np.add(P["P3"],(-3,4)), ea, ha="right", va="bottom", fontsize=8, color="#b00")
    ax.text(*np.add(P["Q2"],(3,4)),  eb, ha="left",  va="bottom", fontsize=8, color="#b00")
    ax.text(*np.add(np.divide(np.add(P["P0"],P["P3"]),2),(-12,0)), f"H1={h1}", ha="right", va="center", fontsize=7.5)
    ax.text(*np.add(np.divide(np.add(P["Q0"],P["Q3"]),2),(10,0)), f"H2={h2}", ha="left", va="center", fontsize=7.5)
    ax.text(*np.add(np.divide(np.add(P["P0"],P["Q0"]),2),(0,-12)), f"L={L}", ha="center", fontsize=7.5)
    ax.set_aspect("equal"); ax.axis("off")

def export_pdf(piezas, path):
    with PdfPages(path) as pdf:
        for p in piezas:
            for blank in desarrollar(p):
                fig = plt.figure(figsize=(11.69, 8.27))
                fig.suptitle("PARTE DE TALLER — DESPIECE", fontsize=13, fontweight="bold", y=0.97)
                axi = fig.add_axes([0.04,0.30,0.40,0.58])
                if p.tipo == "tapa":
                    axi.add_patch(plt.Rectangle((0,0),p.w,p.h,fill=False,lw=1.2))
                    axi.text(p.w/2,p.h+8,f"Tapa {p.w}x{p.h}",ha="center",fontsize=9)
                    axi.text(p.w/2,-12,f"W={p.w}",ha="center",fontsize=7.5)
                    axi.text(-8,p.h/2,f"H={p.h}",ha="right",va="center",rotation=90,fontsize=7.5)
                    axi.set_xlim(-60,p.w+60); axi.set_ylim(-60,p.h+60)
                    axi.set_aspect("equal"); axi.axis("off")
                elif blank["tipo"] == "curva":
                    _iso_curva(axi, blank)
                elif blank["tipo"] == "cono":
                    _iso_cono(axi, blank["wa"], blank["ha"], blank["wb"], blank["hb"],
                              blank["seg_nominal"], blank["a"], blank["b"])
                else:
                    _iso(axi, blank["w"], blank["h"], blank["seg_nominal"], blank["a"], blank["b"])
                axi.set_title("Vista isométrica", fontsize=9)
                axd = fig.add_axes([0.50,0.30,0.46,0.58])
                _draw_dev(axd, blank, p)
                axd.set_title("Desarrollo de chapa (corte)", fontsize=9)
                _cajetin(fig, p, blank)
                pdf.savefig(fig); plt.close(fig)

def _iso_curva(ax, b):
    """Perfil del codo (vista de mejilla): sector de corona ri..ro, ángulo theta."""
    ri, ro, th = b["ri"], b["ro"], b["theta"]
    pts = _annular_pts(0, 0, ri, ro, th)
    ax.add_patch(plt.Polygon(pts, fill=False, lw=1.3))
    # radios extremos
    ax.plot([ri, ro], [0, 0], color="#1a1a1a", lw=1.1)
    ax.plot([ri*math.cos(th), ro*math.cos(th)], [ri*math.sin(th), ro*math.sin(th)],
            color="#1a1a1a", lw=1.1)
    ax.text(ro*0.5, -ro*0.08, f"W={b['W']}", ha="center", fontsize=8)
    ax.text(ro*1.02, ro*0.12, f"talón r={int(b['ro'])}", ha="left", fontsize=7, color="#a33")
    ax.text(ri*0.7, ri*0.5, f"garganta\nr={int(b['ri'])}", ha="center", fontsize=7, color="#36c")
    ax.text(-ro*0.05, ro*0.55, f"{b['ang']}°", ha="right", fontsize=9, color="#1F3864")
    ax.text(ro*0.5, ro*0.75, f"profunditat H={b['H']}", ha="center", fontsize=7.5, color="#555")
    ax.set_aspect("equal"); ax.axis("off")

def _draw_dev(ax, b, p):
    if b["tipo"] == "curva":
        # 4 piezas apiladas: mejilla x2, garganta, talón
        ri, ro, th = b["ri"], b["ro"], b["theta"]
        depth, arc_in, arc_out = b["depth"], b["arc_in"], b["arc_out"]
        # --- mejilla (sector de corona) arriba ---
        pts = _annular_pts(0, 0, ri, ro, th)
        ax.add_patch(plt.Polygon(pts, fill=False, lw=1.2, ec="#1a1a1a"))
        ax.text(ro*0.45, ro*0.45, "MEJILLA  x2", ha="center", fontsize=7.5, color="#1a1a1a")
        ax.text(ro*1.05, 0, f"r ext={int(ro)}", ha="left", va="center", fontsize=6.5, color="#a33")
        ax.text(ri*0.95, ri*0.1, f"r int={int(ri)}", ha="right", va="bottom", fontsize=6.5, color="#36c")
        # --- garganta y talón debajo, como rectángulos ---
        y0 = -depth - 120
        ax.add_patch(plt.Rectangle((0, y0), arc_in, depth, fill=False, lw=1.2))
        ax.add_patch(plt.Rectangle((0, y0), CURVA_SEAM, depth, facecolor="#f3d9d9", ec="none"))
        _dim_h(ax, 0, arc_in, y0 - 30, f"garganta L={arc_in}")
        _dim_v(ax, y0, y0+depth, -25, f"{depth}")
        y1 = y0 - depth - 110
        ax.add_patch(plt.Rectangle((0, y1), arc_out, depth, fill=False, lw=1.2))
        ax.add_patch(plt.Rectangle((0, y1), CURVA_SEAM, depth, facecolor="#f3d9d9", ec="none"))
        _dim_h(ax, 0, arc_out, y1 - 30, f"talón L={arc_out}")
        _dim_v(ax, y1, y1+depth, -25, f"{depth}")
        ax.text(arc_out*0.5, y1 - 75, "(profunditat = H + costura)", ha="center",
                fontsize=6.5, color="#888")
        ax.set_xlim(-90, max(ro, arc_out) + 60)
        ax.set_ylim(y1 - 110, ro + 40)
        ax.set_aspect("equal"); ax.axis("off")
        return
    if b["tipo"] == "tapa":
        bw,bh,pe = b["bw"],b["bh"],b["pest"]
        ax.add_patch(plt.Rectangle((0,0),bw,bh,fill=False,lw=1.3))
        ax.add_patch(plt.Rectangle((pe,pe),bw-2*pe,bh-2*pe,fill=False,lw=0.7,ls="--",ec="#06c"))
        _dim_h(ax,0,bw,bh+18,f"{bw}")
        _dim_v(ax,0,bh,-18,f"{bh}")
        ax.text(bw/2,bh/2,f"pestaña {pe}",ha="center",fontsize=7.5,color="#06c")
        ax.set_xlim(-70,bw+50); ax.set_ylim(-50,bh+60)
    elif b["tipo"] == "cono":
        ga, gb, L = b["ga"], b["gb"], b["length"]
        pad = max(ga, gb, L) * 0.06
        # contorno trapecio
        ax.add_patch(plt.Polygon([(0,0),(ga,0),(gb,L),(0,L)], fill=False, lw=1.3))
        fa = _cono_fold_positions(b["wa"], b["ha"])
        fb = _cono_fold_positions(b["wb"], b["hb"])
        # pittsburgh (bolsa izda, pestaña dcha)
        ax.add_patch(plt.Polygon([(0,0),(PITTS_BOLSA,0),(PITTS_BOLSA,L),(0,L)],
                                 facecolor="#f3d9d9", ec="none"))
        ax.add_patch(plt.Polygon([(ga-PITTS_PEST,0),(ga,0),(gb,L),(gb-PITTS_PEST,L)],
                                 facecolor="#d9e6f3", ec="none"))
        # pliegues internos (abanican)
        for k in (1,2,3):
            ax.plot([fa[k],fb[k]],[0,L],ls="--",lw=0.7,color="#06c")
        # cotas: girth en ambos extremos + longitud (escaladas)
        _dim_h(ax, 0, ga, -pad, f"desarrollo {ga}", off=pad*0.15)
        _dim_h(ax, 0, gb, L+pad*0.3, f"desarrollo {gb}", off=pad*0.15)
        Ltxt = f"L≈{L}  (estimat)" if b.get("len_aprox") else f"L={L}"
        _dim_v(ax, 0, L, -pad, Ltxt)
        ax.text(ga*0.5, L*0.5, f"secció {b['wa']}x{b['ha']} → {b['wb']}x{b['hb']}",
                ha="center", va="center", fontsize=7, color="#555")
        ax.set_xlim(-pad*2.2, max(ga,gb)+pad); ax.set_ylim(-pad*2, L+pad*1.8)
    else:
        g,L = b["girth"],b["length"]
        pad = max(g, L) * 0.06
        ax.add_patch(plt.Rectangle((0,0),g,L,fill=False,lw=1.3))
        ax.add_patch(plt.Rectangle((0,0),PITTS_BOLSA,L,facecolor="#f3d9d9",ec="none"))
        ax.add_patch(plt.Rectangle((g-PITTS_PEST,0),PITTS_PEST,L,facecolor="#d9e6f3",ec="none"))
        xs=[PITTS_BOLSA+b["w"],PITTS_BOLSA+b["w"]+b["h"],PITTS_BOLSA+2*b["w"]+b["h"]]
        for fx in xs: ax.plot([fx,fx],[0,L],ls="--",lw=0.7,color="#06c")
        segx=[(0,PITTS_BOLSA,"35"),(PITTS_BOLSA,PITTS_BOLSA+b["w"],str(b["w"])),
              (PITTS_BOLSA+b["w"],PITTS_BOLSA+b["w"]+b["h"],str(b["h"])),
              (PITTS_BOLSA+b["w"]+b["h"],PITTS_BOLSA+2*b["w"]+b["h"],str(b["w"])),
              (PITTS_BOLSA+2*b["w"]+b["h"],g-PITTS_PEST,str(b["h"])),
              (g-PITTS_PEST,g,"10")]
        for x1,x2,t in segx: _dim_h(ax, x1, x2, L+pad*0.4, t, off=pad*0.12)
        _dim_h(ax, 0, g, L+pad*1.6, f"Desarrollo total = {g}", off=pad*0.15)
        _dim_v(ax, 0, L, -pad, f"L={L}")
        ax.set_xlim(-pad*1.6, g+pad); ax.set_ylim(-pad*1.6, L+pad*2.8)
    ax.set_aspect("equal"); ax.axis("off")

def _cajetin(fig, p, b):
    ax = fig.add_axes([0.04,0.04,0.92,0.20]); ax.axis("off")
    ax.add_patch(plt.Rectangle((0,0),1,1,fill=False,lw=1,transform=ax.transAxes))
    if p.tipo == "cono":
        seccion = f"{p.w}x{p.h} → {p.w2}x{p.h2} mm"
        if getattr(p, "len_aprox", False):
            seccion += "  · L estimat (ajustar)"
    elif p.tipo == "curva":
        seccion = f"{p.w} x {p.h} mm · gir {p.angle}°"
    else:
        seccion = f"{p.w} x {p.h} mm"
    rows = [
        ("Proyecto", PROYECTO, "Cliente", CLIENTE),
        ("Ref. pieza", p.ref, "Fecha", FECHA),
        ("Descripción", p.descr, "Cantidad", f"{p.qty} ut"),
        ("Sección", seccion, "Espesor", f"{p.gauge} mm"),
        ("Uniones (A/B)", (p.ext_a if p.tipo=="tapa" else f"{p.ext_a} / {p.ext_b}"), "Material", p.material),
        ("Costura", f"Pittsburgh ({PITTS_BOLSA}+{PITTS_PEST} mm)",
         "Troceado máx.", f"{MAX_TRAMO} mm"),
    ]
    for i,(k1,v1,k2,v2) in enumerate(rows):
        y = 1 - (i+1)/len(rows) + 0.02
        ax.text(0.01,y,k1+":",fontweight="bold",fontsize=7.5,transform=ax.transAxes)
        ax.text(0.14,y,str(v1),fontsize=7.5,transform=ax.transAxes)
        ax.text(0.55,y,k2+":",fontweight="bold",fontsize=7.5,transform=ax.transAxes)
        ax.text(0.70,y,str(v2),fontsize=7.5,transform=ax.transAxes)

# ----------------------- LISTA DE DESPIECE (CSV/consola) -----------------------
def export_csv_y_tabla(piezas, path):
    filas=[]
    for p in piezas:
        for b in desarrollar(p):
            if b["tipo"]=="tapa":
                desarrollo=f"{b['bw']} x {b['bh']} (pest {b['pest']})"
            elif b["tipo"]=="cono":
                desarrollo=f"trapecio {b['ga']}→{b['gb']} x {b['length']}"
            elif b["tipo"]=="curva":
                desarrollo=(f"2 mejillas r{int(b['ri'])}-{int(b['ro'])} ang {b['ang']}° · "
                            f"garganta {b['arc_in']}x{b['depth']} · talón {b['arc_out']}x{b['depth']}")
            else:
                desarrollo=f"{b['girth']} x {b['length']}"
            filas.append([p.ref, b["etiqueta"], p.qty, p.gauge,
                          f"{p.ext_a}/{p.ext_b}", desarrollo])
    hdr=["Ref","Pieza","Ut","Esp(mm)","Uniones","Desarrollo chapa WxL (mm)"]
    with open(path,"w",newline="",encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(hdr); w.writerows(filas)
    anchos=[max(len(str(x)) for x in [hdr[i]]+[fl[i] for fl in filas]) for i in range(len(hdr))]
    line="  ".join(h.ljust(anchos[i]) for i,h in enumerate(hdr))
    print(line); print("-"*len(line))
    for fl in filas:
        print("  ".join(str(c).ljust(anchos[i]) for i,c in enumerate(fl)))

# ----------------------- API del módulo -----------------------
def build_cnc_dxf(piezas, path):
    export_dxf(piezas, path); return path
def build_shop_pdf(piezas, path, project=None, client=None, date=None):
    global PROYECTO, CLIENTE, FECHA
    if project: PROYECTO = project
    if client: CLIENTE = client
    if date: FECHA = date
    export_pdf(piezas, path); return path
def parts_csv(piezas, path):
    export_csv_y_tabla(piezas, path); return path
