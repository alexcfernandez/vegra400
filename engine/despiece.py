#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DESPIECE AUTOMÁTICO DE CONDUCTES — v0.1
Tipos soportados en esta versión: conducte recto, carret, tapa.
Genera: (1) lista de despiece (CSV + consola), (2) DXF de corte para CNC,
        (3) parte de taller en PDF con cotas e isométrico.

BASE DE CONOCIMIENTO (reglas) — confirmadas por el cliente salvo lo marcado [ASUNCIÓN]
"""
import math, csv, datetime
import numpy as np
import ezdxf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

# ----------------------- REGLAS / PARÁMETROS -----------------------
MAX_TRAMO   = 1500   # mm  troceado máximo de un tramo recto            [CONFIRMADO]
PITTS_BOLSA = 35     # mm  carga Pittsburgh lado bolsa                   [CONFIRMADO]
PITTS_PEST  = 10     # mm  carga Pittsburgh lado pestaña                 [CONFIRMADO]
SEAM        = PITTS_BOLSA + PITTS_PEST   # = 45 mm añadidos por 1 costura

N_COSTURES  = 1      # nº de costuras Pittsburgh del cuerpo (1 = una pieza) [ASUNCIÓN]
METU_DEDUCT = 0      # el metu se integra: el largo de chapa = largo de pieza      [CONFIRMADO]
PAO_MARGIN  = 0      # mm extra dejado en extremo PAO para rematar en obra  [ASUNCIÓN -> confirmar]
TAPA_PEST   = 25     # mm pestaña de la tapa                                [ASUNCIÓN -> confirmar]

PROYECTO = "EMBOTITS COLLELL - ASSECADOR"
CLIENTE  = "FRITECNO / Sr. Carles Pagès"
FECHA    = datetime.date.today().strftime("%d/%m/%Y")

# ----------------------- MODELO DE DATOS -----------------------
class Pieza:
    def __init__(self, ref, tipo, w, h, L=None, ext_a="M20", ext_b="M20",
                 gauge=0.8, qty=1, material="Xapa simple galva"):
        self.ref, self.tipo = ref, tipo
        self.w, self.h, self.L = w, h, L
        self.ext_a, self.ext_b = ext_a, ext_b
        self.gauge, self.qty, self.material = gauge, qty, material

    @property
    def descr(self):
        if self.tipo == "tapa":
            return f"Tapa {self.w}x{self.h} {self.ext_a}"
        return f"{self.tipo.capitalize()} {self.w}x{self.h} - {self.L}L {self.ext_a}/{self.ext_b}"

# ----------------------- LÓGICA DE FABRICACIÓN -----------------------
def trocear(L):
    """Divide una longitud en tramos <= MAX_TRAMO, lo más iguales posible."""
    n = max(1, math.ceil(L / MAX_TRAMO))
    base = round(L / n)
    segs = [base] * (n - 1) + [L - base * (n - 1)]
    return segs

def desarrollo_cuerpo(p):
    """Devuelve lista de blanks (chapa plana) para un conducte/carret.
       Cada blank: dict con girth, length, side lengths, allowances, fold_x, etiqueta."""
    girth = 2 * (p.w + p.h) + N_COSTURES * SEAM      # ancho desarrollado
    segs = trocear(p.L)
    blanks = []
    for i, seg in enumerate(segs):
        # extremos reales de la pieza vs juntas internas del troceado
        a = p.ext_a if i == 0 else "M20"   # junta interna del troceado = metu [CONFIRMADO]
        b = p.ext_b if i == len(segs) - 1 else "M20"
        length = seg
        if a == "M20": length -= METU_DEDUCT
        if b == "M20": length -= METU_DEDUCT
        if a == "PAO": length += PAO_MARGIN
        if b == "PAO": length += PAO_MARGIN
        etiqueta = p.descr + (f"  [tramo {i+1}/{len(segs)}]" if len(segs) > 1 else "")
        blanks.append(dict(girth=girth, length=length, w=p.w, h=p.h,
                           a=a, b=b, ref=p.ref, etiqueta=etiqueta,
                           gauge=p.gauge, tipo=p.tipo, seg_nominal=seg))
    return blanks

def desarrollo_tapa(p):
    bw = p.w + 2 * TAPA_PEST
    bh = p.h + 2 * TAPA_PEST
    return [dict(tipo="tapa", w=p.w, h=p.h, bw=bw, bh=bh, pest=TAPA_PEST,
                 ref=p.ref, etiqueta=p.descr, gauge=p.gauge, a=p.ext_a, b="-")]

def desarrollar(p):
    return desarrollo_tapa(p) if p.tipo == "tapa" else desarrollo_cuerpo(p)

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
            for _copy in range(p.qty):                  # una copia por unidad
                if blank["tipo"] == "tapa":
                    w, bw, bh, pe = blank["bw"], blank["bw"], blank["bh"], blank["pest"]
                    _draw_tapa(msp, x0, y0, blank)
                    used_w, used_h = bw, bh
                else:
                    _draw_recto(msp, x0, y0, blank)
                    used_w, used_h = blank["girth"], blank["length"]
                msp.add_text(blank["etiqueta"], height=12,
                             dxfattribs={"layer": "TEXTO"}).set_placement((x0, y0 - 18))
                x0 += used_w + gap
                rowmax = max(rowmax, used_h)
                if x0 > 6000:                            # salto de fila
                    x0 = 0.0; y0 += rowmax + gap + 30; rowmax = 0.0
    doc.saveas(path)

def _draw_recto(msp, x, y, b):
    g, L = b["girth"], b["length"]
    msp.add_lwpolyline([(x,y),(x+g,y),(x+g,y+L),(x,y+L)], close=True,
                       dxfattribs={"layer":"CORTE"})
    # líneas de plegado (3 esquinas) + posiciones de costura
    p1 = x + PITTS_BOLSA + b["w"]
    p2 = p1 + b["h"]
    p3 = p2 + b["w"]
    for fx in (p1, p2, p3):
        msp.add_line((fx,y),(fx,y+L), dxfattribs={"layer":"PLEGADO"})
    # marcar cargas Pittsburgh (líneas de costura en COTA_INFO)
    msp.add_line((x+PITTS_BOLSA,y),(x+PITTS_BOLSA,y+L), dxfattribs={"layer":"COTA_INFO"})
    msp.add_line((x+g-PITTS_PEST,y),(x+g-PITTS_PEST,y+L), dxfattribs={"layer":"COTA_INFO"})

def _draw_tapa(msp, x, y, b):
    bw, bh, pe = b["bw"], b["bh"], b["pest"]
    # contorno con esquinas recortadas
    pts = [(x+pe,y),(x+bw-pe,y),(x+bw-pe,y+pe),(x+bw,y+pe),(x+bw,y+bh-pe),
           (x+bw-pe,y+bh-pe),(x+bw-pe,y+bh),(x+pe,y+bh),(x+pe,y+bh-pe),
           (x,y+bh-pe),(x,y+pe),(x+pe,y+pe)]
    msp.add_lwpolyline(pts, close=True, dxfattribs={"layer":"CORTE"})
    # plegado interior
    msp.add_lwpolyline([(x+pe,y+pe),(x+bw-pe,y+pe),(x+bw-pe,y+bh-pe),(x+pe,y+bh-pe)],
                       close=True, dxfattribs={"layer":"PLEGADO"})

# ----------------------- SALIDA: PARTE DE TALLER (PDF) -----------------------
def _dim_h(ax, x1, x2, y, txt, off=0):
    ax.annotate("", (x1,y),(x2,y), arrowprops=dict(arrowstyle="<->", color="#222", lw=0.8))
    ax.text((x1+x2)/2, y+off+ (abs(x2-x1)*0+6), txt, ha="center", va="bottom", fontsize=7.5)

def _dim_v(ax, y1, y2, x, txt):
    ax.annotate("", (x,y1),(x,y2), arrowprops=dict(arrowstyle="<->", color="#222", lw=0.8))
    ax.text(x-8,(y1+y2)/2, txt, ha="right", va="center", rotation=90, fontsize=7.5)

def _iso(ax, w, h, L, ea, eb):
    # proyección isométrica simple: X profundidad(L), Y ancho(w), Z alto(h)
    c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
    def proj(x,y,z): return ((x-y)*c, z+(x+y)*s)
    P = {k: proj(*v) for k,v in {
        "A":(0,0,0),"B":(L,0,0),"C":(L,w,0),"D":(0,w,0),
        "E":(0,0,h),"F":(L,0,h),"G":(L,w,h),"H":(0,w,h)}.items()}
    edges=[("A","B"),("B","C"),("C","D"),("D","A"),("E","F"),("F","G"),
           ("G","H"),("H","E"),("A","E"),("B","F"),("C","G"),("D","H")]
    for a,b in edges:
        xs=[P[a][0],P[b][0]]; ys=[P[a][1],P[b][1]]
        ax.plot(xs,ys,color="#1a1a1a",lw=1.1)
    # etiquetas extremos
    ax.text(*np.add(P["A"],(-3,-3)), ea, ha="right", va="top", fontsize=8, color="#b00")
    ax.text(*np.add(P["B"],(3,-3)),  eb, ha="left",  va="top", fontsize=8, color="#b00")
    # cotas aproximadas
    ax.text(*np.add(np.divide(np.add(P["A"],P["B"]),2),(0,-14)), f"L={L}", ha="center", fontsize=7.5)
    ax.text(*np.add(np.divide(np.add(P["A"],P["E"]),2),(-12,0)), f"H={h}", ha="right", va="center", fontsize=7.5)
    ax.text(*np.add(np.divide(np.add(P["A"],P["D"]),2),(-6,4)), f"W={w}", ha="center", fontsize=7.5)
    ax.set_aspect("equal"); ax.axis("off")

def export_pdf(piezas, path):
    with PdfPages(path) as pdf:
        for p in piezas:
            for blank in desarrollar(p):
                fig = plt.figure(figsize=(11.69, 8.27))  # A4 apaisado
                fig.suptitle("PARTE DE TALLER — DESPIECE", fontsize=13, fontweight="bold", y=0.97)
                # --- isométrico ---
                axi = fig.add_axes([0.04,0.30,0.40,0.58])
                if p.tipo=="tapa":
                    axi.add_patch(plt.Rectangle((0,0),p.w,p.h,fill=False,lw=1.2))
                    axi.text(p.w/2,p.h+8,f"Tapa {p.w}x{p.h}",ha="center",fontsize=9)
                    axi.text(p.w/2,-12,f"W={p.w}",ha="center",fontsize=7.5)
                    axi.text(-8,p.h/2,f"H={p.h}",ha="right",va="center",rotation=90,fontsize=7.5)
                    axi.set_xlim(-60,p.w+60); axi.set_ylim(-60,p.h+60)
                    axi.set_aspect("equal"); axi.axis("off")
                else:
                    _iso(axi, blank["w"], blank["h"], blank["seg_nominal"], blank["a"], blank["b"])
                axi.set_title("Vista isométrica", fontsize=9)
                # --- desarrollo de chapa ---
                axd = fig.add_axes([0.50,0.30,0.46,0.58])
                _draw_dev(axd, blank, p)
                axd.set_title("Desarrollo de chapa (corte)", fontsize=9)
                # --- cajetín ---
                _cajetin(fig, p, blank)
                pdf.savefig(fig); plt.close(fig)

def _draw_dev(ax, b, p):
    if b["tipo"]=="tapa":
        bw,bh,pe = b["bw"],b["bh"],b["pest"]
        ax.add_patch(plt.Rectangle((0,0),bw,bh,fill=False,lw=1.3))
        ax.add_patch(plt.Rectangle((pe,pe),bw-2*pe,bh-2*pe,fill=False,lw=0.7,ls="--",ec="#06c"))
        _dim_h(ax,0,bw,bh+18,f"{bw}")
        _dim_v(ax,0,bh,-18,f"{bh}")
        ax.text(bw/2,bh/2,f"pestaña {pe}",ha="center",fontsize=7.5,color="#06c")
        ax.set_xlim(-70,bw+50); ax.set_ylim(-50,bh+60)
    else:
        g,L = b["girth"],b["length"]
        ax.add_patch(plt.Rectangle((0,0),g,L,fill=False,lw=1.3))
        # cargas pittsburgh
        ax.add_patch(plt.Rectangle((0,0),PITTS_BOLSA,L,facecolor="#f3d9d9",ec="none"))
        ax.add_patch(plt.Rectangle((g-PITTS_PEST,0),PITTS_PEST,L,facecolor="#d9e6f3",ec="none"))
        # pliegues
        xs=[PITTS_BOLSA+b["w"],PITTS_BOLSA+b["w"]+b["h"],PITTS_BOLSA+2*b["w"]+b["h"]]
        for fx in xs: ax.plot([fx,fx],[0,L],ls="--",lw=0.7,color="#06c")
        # cotas de caras
        segx=[(0,PITTS_BOLSA,"35"),(PITTS_BOLSA,PITTS_BOLSA+b["w"],str(b["w"])),
              (PITTS_BOLSA+b["w"],PITTS_BOLSA+b["w"]+b["h"],str(b["h"])),
              (PITTS_BOLSA+b["w"]+b["h"],PITTS_BOLSA+2*b["w"]+b["h"],str(b["w"])),
              (PITTS_BOLSA+2*b["w"]+b["h"],g-PITTS_PEST,str(b["h"])),
              (g-PITTS_PEST,g,"10")]
        for x1,x2,t in segx: _dim_h(ax,x1,x2,L+22,t)
        _dim_h(ax,0,g,L+70,f"Desarrollo total = {g}")
        _dim_v(ax,0,L,-22,f"{L}")
        ax.text(PITTS_BOLSA/2,L*0.5,"P.bolsa\n35",ha="center",va="center",fontsize=6.5,color="#a33")
        ax.text(g-PITTS_PEST/2,L*0.5,"pest.\n10",ha="center",va="center",fontsize=6.5,color="#36c")
        ax.set_xlim(-70,g+30); ax.set_ylim(-30,L+95)
    ax.set_aspect("equal"); ax.axis("off")

def _cajetin(fig, p, b):
    ax = fig.add_axes([0.04,0.04,0.92,0.20]); ax.axis("off")
    ax.add_patch(plt.Rectangle((0,0),1,1,fill=False,lw=1,transform=ax.transAxes))
    rows = [
        ("Proyecto", PROYECTO, "Cliente", CLIENTE),
        ("Ref. pieza", p.ref, "Fecha", FECHA),
        ("Descripción", p.descr, "Cantidad", f"{p.qty} ut"),
        ("Sección WxH", f"{p.w} x {p.h} mm", "Espesor", f"{p.gauge} mm"),
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
            else:
                desarrollo=f"{b['girth']} x {b['length']}"
            filas.append([p.ref, b["etiqueta"], p.qty, p.gauge,
                          f"{p.ext_a}/{p.ext_b}", desarrollo])
    hdr=["Ref","Pieza","Ut","Esp(mm)","Uniones","Desarrollo chapa WxL (mm)"]
    with open(path,"w",newline="",encoding="utf-8") as f:
        w=csv.writer(f); w.writerow(hdr); w.writerows(filas)
    # tabla por consola
    anchos=[max(len(str(x)) for x in [hdr[i]]+[fl[i] for fl in filas]) for i in range(len(hdr))]
    line="  ".join(h.ljust(anchos[i]) for i,h in enumerate(hdr))
    print(line); print("-"*len(line))
    for fl in filas:
        print("  ".join(str(c).ljust(anchos[i]) for i,c in enumerate(fl)))

# ----------------------- CASO DE VALIDACIÓN (piezas reales de los croquis) -----------------------

# API del módulo
def build_cnc_dxf(piezas, path):
    export_dxf(piezas, path); return path
def build_shop_pdf(piezas, path):
    export_pdf(piezas, path); return path
def parts_csv(piezas, path):
    export_csv_y_tabla(piezas, path); return path
