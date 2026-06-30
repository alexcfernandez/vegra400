# -*- coding: utf-8 -*-
"""App web: subir plano (PDF/DXF) -> revisar lista de piezas -> generar
   presupuesto (Excel), planos de taller (PDF) y archivo CNC (DXF)."""
import os
from flask import Flask, request, render_template_string, send_from_directory, redirect, url_for
from werkzeug.utils import secure_filename
import pipeline
from engine import extract, read_dxf

BASE = os.path.dirname(os.path.abspath(__file__))
UP = os.path.join(BASE, "uploads"); GEN = os.path.join(BASE, "generated")
os.makedirs(UP, exist_ok=True); os.makedirs(GEN, exist_ok=True)
SAMPLE = os.path.join(BASE, "sample_assecador.csv")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 30 * 1024 * 1024

CSS = """<style>
body{font-family:Arial,Helvetica,sans-serif;max-width:900px;margin:30px auto;color:#222;padding:0 16px}
h1{color:#1F3864} .box{background:#f6f8fc;border:1px solid #d9e1f2;border-radius:8px;padding:18px;margin:16px 0}
.btn{background:#1F3864;color:#fff;border:0;padding:11px 18px;border-radius:6px;font-size:15px;cursor:pointer;text-decoration:none;display:inline-block}
.muted{color:#666;font-size:13px} textarea{width:100%;height:340px;font-family:monospace;font-size:12px}
.note{background:#FFF2CC;border:1px solid #e6d28a;padding:10px;border-radius:6px;font-size:13px}
a.dl{display:block;padding:10px 0;font-size:16px}
</style>"""

UPLOAD = CSS + """
<h1>Despiece &amp; Pressupost — Assecador</h1>
<p class="muted">Puja el plano del projecte i el sistema et torna el pressupost (Excel), els planos de taller i el fitxer per la CNC (DXF).</p>
<div class="box">
  <form method="post" action="/process" enctype="multipart/form-data">
    <p><b>1) Puja el plano</b> (PDF o DXF):</p>
    <input type="file" name="plano" accept=".pdf,.dxf">
    <p style="margin-top:14px"><button class="btn" type="submit">Processar plano →</button></p>
  </form>
</div>
<div class="box">
  <p class="muted">O prova-ho amb la llista d'exemple de l'assecador:</p>
  <form method="post" action="/review"><input type="hidden" name="use_sample" value="1">
  <button class="btn" type="submit" style="background:#5b6b8c">Usar exemple →</button></form>
</div>
"""

REVIEW = CSS + """
<h1>2) Revisa la llista de peces</h1>
{% if cotas %}<div class="note"><b>Cotes detectades al plano (mm):</b> {{cotas}}<br>
<span class="muted">Del PDF surten cotes soltes; revisa/edita la llista abans de generar. Amb DXF això vindrà ja muntat.</span></div>{% endif %}
<p class="muted">Format: <code>grup;codi;descr;w1;h1;w2;h2;uts;unit;preu</code> · codis: rec, red, c90, c45, inj, des, tapa, tmalla, esp · treb=mà d'obra · preu només per a peces especials i mà d'obra.</p>
<form method="post" action="/generate">
  <textarea name="csv">{{csv}}</textarea>
  <p style="margin-top:12px"><button class="btn" type="submit">Generar pressupost + planos taller + DXF →</button></p>
</form>
"""

RESULT = CSS + """
<h1>3) Llest ✓</h1>
<div class="box">
  <a class="dl" href="/download/presupuesto_auto.xlsx">📊 Pressupost (Excel) — preu aproximat per revisar</a>
  {% if parte %}<a class="dl" href="/download/parte_taller.pdf">📐 Planos de taller (PDF)</a>{% endif %}
  {% if dxf %}<a class="dl" href="/download/despiece_corte.dxf">🛠️ Fitxer CNC (DXF)</a>{% endif %}
  {% if csvf %}<a class="dl" href="/download/despiece.csv">📋 Llista de despiece (CSV)</a>{% endif %}
</div>
<p class="note">El pressupost reprodueix la tarifa de VEGRA. Les peces especials i la mà d'obra encara són dades d'entrada (en blau a l'Excel). Els planos/DXF es generen per als trams rectes i tapes; els accessoris (corbes, pantalons…) són el següent mòdul.</p>
<p><a href="/">← Tornar</a></p>
"""

@app.route("/")
def home():
    return UPLOAD

@app.route("/process", methods=["POST"])
def process():
    f = request.files.get("plano")
    cotas = ""; csv_text = open(SAMPLE, encoding="utf-8").read()
    if f and f.filename:
        name = secure_filename(f.filename); path = os.path.join(UP, name); f.save(path)
        if name.lower().endswith(".pdf"):
            try:
                info = extract.extract_cotas(path)
                cotas = ", ".join(str(c) for c in info["cotas"] if c >= 100)
                csv_text = extract.candidate_csv(info["cotas"])
            except Exception as e:
                cotas = f"(no s'han pogut llegir cotes: {e})"
        elif name.lower().endswith(".dxf"):
            try:
                a = read_dxf.analyze(path)
                cotas = ", ".join(str(c) for c in a["cotas"])
                csv_text = read_dxf.review_csv(a)
            except Exception as e:
                cotas = f"(no s'ha pogut llegir el DXF: {e})"
    return render_template_string(REVIEW, cotas=cotas, csv=csv_text)

@app.route("/review", methods=["POST"])
def review():
    return render_template_string(REVIEW, cotas="", csv=open(SAMPLE, encoding="utf-8").read())

@app.route("/generate", methods=["POST"])
def generate():
    csv_text = request.form.get("csv", "")
    out = pipeline.generate_all(csv_text, GEN)
    return render_template_string(RESULT, parte=("parte" in out), dxf=("dxf" in out), csvf=("despiece_csv" in out))

@app.route("/download/<path:fname>")
def download(fname):
    return send_from_directory(GEN, fname, as_attachment=True)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
