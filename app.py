# -*- coding: utf-8 -*-
"""App web: subir plano (PDF/DXF) -> revisar lista de piezas -> generar
   presupuesto (Excel + materiales), planos de taller (PDF) y archivo CNC (DXF).
   Genérico (cualquier proyecto) y a prueba de fallos."""
import os
from flask import Flask, request, render_template_string, send_from_directory
from werkzeug.utils import secure_filename
import pipeline
from engine import extract, read_dxf, ai_assist

BASE = os.path.dirname(os.path.abspath(__file__))
UP = os.path.join(BASE, "uploads"); GEN = os.path.join(BASE, "generated")
os.makedirs(UP, exist_ok=True); os.makedirs(GEN, exist_ok=True)
SAMPLE = os.path.join(BASE, "sample_assecador.csv")
SCAFFOLD = ("grup;codi;descr;w1;h1;w2;h2;uts;unit;preu;peces\n"
            "# Completa la llista de peces (o puja un DXF/PDF per pre-omplir-la)\n"
            "# codis: rec, red, c90, c45, inj, des, tapa, tmalla, esp | treb=ma d'obra\n"
            "# 'peces' = nº de peces FISIQUES reals per al taller (x1/x2); buit = 1. Independent d'uts (= el que factura).\n")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

CSS = """<style>
body{font-family:Arial,Helvetica,sans-serif;max-width:900px;margin:30px auto;color:#222;padding:0 16px}
h1{color:#1F3864} .box{background:#f6f8fc;border:1px solid #d9e1f2;border-radius:8px;padding:18px;margin:16px 0}
.btn{background:#1F3864;color:#fff;border:0;padding:11px 18px;border-radius:6px;font-size:15px;cursor:pointer;text-decoration:none;display:inline-block}
.muted{color:#666;font-size:13px} textarea{width:100%;height:340px;font-family:monospace;font-size:12px}
.note{background:#FFF2CC;border:1px solid #e6d28a;padding:10px;border-radius:6px;font-size:13px}
.err{background:#fdecea;border:1px solid #f5c2c0;padding:10px;border-radius:6px;font-size:13px}
a.dl{display:block;padding:10px 0;font-size:16px}
</style>"""

UPLOAD = CSS + """
<h1>Despiece &amp; Pressupost</h1>
<p class="muted">Puja el plano del projecte i el sistema et torna el pressupost (Excel, amb materials), els planos de taller i el fitxer per la CNC (DXF).</p>
<div class="box">
  <form method="post" action="/process" enctype="multipart/form-data">
    <p><b>1) Puja el plano</b> (PDF o DXF):</p>
    <input type="file" name="plano" accept=".pdf,.dxf" multiple>
    <p class="muted" style="margin:6px 0 0">Pots seleccionar diversos PDFs alhora (planta, retorn, axonometries...).</p>
    <p style="margin-top:14px"><button class="btn" type="submit">Processar plano &rarr;</button></p>
  </form>
</div>
<div class="box">
  <p class="muted">O prova-ho amb una llista d'exemple (dades de prova):</p>
  <form method="post" action="/review"><input type="hidden" name="use_sample" value="1">
  <button class="btn" type="submit" style="background:#5b6b8c">Usar dades d'exemple &rarr;</button></form>
</div>
"""

REVIEW = CSS + """
<h1>2) Revisa la llista de peces</h1>
{% if err %}<div class="err">{{err}}</div>{% endif %}
{% if cotas %}<div class="note"><b>Llegit del plano:</b> {{cotas}}<br>
<span class="muted">El muntatge automatic de la llista de peces des del plano esta en construccio; de moment revisa/completa la llista abans de generar.</span></div>{% endif %}
<p class="muted">Format: <code>grup;codi;descr;w1;h1;w2;h2;uts;unit;preu;peces</code> &middot; codis: rec, red, c90, c45, inj, des, tapa, tmalla, esp &middot; treb=ma d'obra &middot; <b>uts</b> = el que factura (preu) &middot; <b>peces</b> = peces reals per al taller (l'x1/x2; buit = 1) &middot; preu nomes per a peces especials i ma d'obra.</p>
<form method="post" action="/generate">
  <p><b>Obra/Projecte:</b> <input type="text" name="project" value="{{project|default('')}}" placeholder="ex: EMBOTITS COLLELL - ASSECADOR" style="width:48%">
  &nbsp;<b>Client:</b> <input type="text" name="client" value="{{client|default('')}}" placeholder="ex: FRITECNO / Sr. ..." style="width:30%"></p>
  <textarea name="csv">{{csv}}</textarea>
  <p style="margin-top:12px"><button class="btn" type="submit">Generar pressupost + materials + planos + DXF &rarr;</button></p>
</form>
"""

RESULT = CSS + """
<h1>3) Llest &#10003;</h1>
<div class="box">
  <a class="dl" href="/download/presupuesto_auto.xlsx">Pressupost (Excel: Tarifa &middot; Pressupost &middot; Materials)</a>
  {% if parte %}<a class="dl" href="/download/parte_taller.pdf">Planos de taller (PDF)</a>{% endif %}
  {% if dxf %}<a class="dl" href="/download/despiece_corte.dxf">Fitxer CNC (DXF)</a>{% endif %}
  {% if csvf %}<a class="dl" href="/download/despiece.csv">Llista de despiece (CSV)</a>{% endif %}
</div>
<p><a href="/">&larr; Tornar</a></p>
"""

ERRPAGE = CSS + """<h1>Vaja...</h1><div class="err">{{err}}</div>
<p class="muted">Torna a provar amb un altre fitxer o amb "Usar dades d'exemple".</p>
<p><a href="/">&larr; Tornar</a></p>"""

@app.route("/")
def home():
    return UPLOAD

@app.route("/process", methods=["POST"])
def process():
    cotas_set = set(); err = ""; csv_text = SCAFFOLD; imgs = []; analysis = {}; cotas = ""
    try:
        files = [f for f in request.files.getlist("plano") if f and f.filename]
        if not files:
            err = "No has seleccionat cap fitxer."
        else:
            for f in files:
                name = secure_filename(f.filename); path = os.path.join(UP, name); f.save(path)
                low = name.lower()
                if low.endswith(".pdf"):
                    try:
                        info = extract.extract_cotas(path)
                        cotas_set.update(c for c in info["cotas"] if c >= 50)
                    except Exception:
                        pass
                    try:
                        imgs += _pdf_to_pngs(path, name)
                    except Exception:
                        pass
                elif low.endswith(".dxf"):
                    try:
                        a = read_dxf.analyze(path)
                        cotas_set.update(a.get("cotas", []))
                        analysis["cond_layers"] = a.get("cond_layers", {})
                        analysis["duct_len_m"] = a.get("duct_len_m", {})
                        analysis["cotas_by_system"] = a.get("cotas_by_system", {})
                        analysis["runs_by_system"] = a.get("runs_by_system", {})
                        analysis["n_trams_1500"] = a.get("n_trams_1500")
                        img = os.path.join(UP, name + ".png")
                        read_dxf.render_ducts_png(path, img)
                        if os.path.exists(img):
                            imgs.append(img)
                    except Exception:
                        pass
                else:
                    err = "Format no suportat (puja PDF o DXF)."
            imgs = imgs[:10]
            analysis["cotas"] = sorted(cotas_set)
            cotas = ", ".join(str(c) for c in analysis["cotas"]) + ("  ·  %d imatges del plano" % len(imgs) if imgs else "")
            try:
                csv_text = ai_assist.build_pieces(analysis, images=imgs)
            except Exception:
                csv_text = SCAFFOLD
    except Exception:
        err = "Hi ha hagut un error processant els fitxers."
    return render_template_string(REVIEW, cotas=cotas, csv=csv_text, err=err, project="", client="")

def _pdf_to_pngs(path, tag="p", max_pages=4):
    """Render de cada pàgina: la pàgina sencera (per la topologia) MÉS 4 quadrants a
       més resolució (per llegir les cotes petites en vermell). Així la IA pot
       enganxar les cotes ESCRITES a cada accessori en comptes de perdre-les en
       l'escalat d'una pàgina sencera reduïda."""
    import fitz, re
    from PIL import Image
    safe = re.sub(r"[^a-zA-Z0-9]", "", tag)[:20] or "p"
    out = []
    doc = fitz.open(path)
    for i in range(min(max_pages, doc.page_count)):
        page = doc[i]
        pf = os.path.join(UP, "img_%s_%d.png" % (safe, i))
        page.get_pixmap(dpi=150).save(pf); out.append(pf)
        try:
            pix = page.get_pixmap(dpi=300)
            im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            W, H = pix.width, pix.height
            ox, oy = int(W * 0.06), int(H * 0.06)
            quads = [(0, 0, W//2+ox, H//2+oy), (W//2-ox, 0, W, H//2+oy),
                     (0, H//2-oy, W//2+ox, H), (W//2-ox, H//2-oy, W, H)]
            for q, (x0, y0, x1, y1) in enumerate(quads):
                tf = os.path.join(UP, "img_%s_%d_q%d.png" % (safe, i, q))
                im.crop((x0, y0, x1, y1)).save(tf); out.append(tf)
        except Exception:
            pass
    return out

@app.route("/review", methods=["POST"])
def review():
    try:
        csv_text = open(SAMPLE, encoding="utf-8").read()
    except Exception:
        csv_text = SCAFFOLD
    return render_template_string(REVIEW, cotas="", csv=csv_text, err="", project="", client="")

@app.route("/generate", methods=["POST"])
def generate():
    try:
        csv_text = request.form.get("csv", "")
        project = request.form.get("project", "").strip() or None
        client = request.form.get("client", "").strip() or None
        out = pipeline.generate_all(csv_text, GEN, project=project, client=client)
        return render_template_string(RESULT, parte=("parte" in out), dxf=("dxf" in out), csvf=("despiece_csv" in out))
    except Exception:
        return render_template_string(ERRPAGE, err="No s'ha pogut generar. Revisa que la llista tingui el format correcte (columnes separades per ;).")

@app.route("/download/<path:fname>")
def download(fname):
    return send_from_directory(GEN, fname, as_attachment=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
