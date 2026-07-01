# -*- coding: utf-8 -*-
"""Capa de IA (Anthropic) que LLEGEIX el plano (axonometria/planta) i munta la
llista de peces. Treballa en dues fases: (1) inventari accessori per accessori amb
les cotes ESCRITES, (2) llista CSV. NO inventa mesures: el que no esta acotat ho
marca '(seccio a confirmar)' perque ho ompli el tecnic.
Clau a ANTHROPIC_API_KEY, model a AI_MODEL. Si falla, l'app cau al mode manual."""
import os, json, base64, urllib.request

SYSTEM = (
 "Ets un tecnic expert en conductes metallics rectangulars (estil VEGRA 400) que LLEGEIX plans\n"
 "(axonometries i plantes). Treus el MAXIM del que el pla MOSTRA, SENSE inventar res.\n"
 "Reps la pagina sencera i tambe quadrants ampliats: fes servir els quadrants per llegir les\n"
 "cotes petites (sovint en vermell) i la pagina sencera per entendre la topologia.\n"
 "\n"
 "RESPON EN DUES FASES:\n"
 "FASE 1 - INVENTARI. Una linia per accessori, comencant amb '# ':\n"
 "  # <sistema/color> · <tipus> · cotes ESCRITES: <les que vegis> (o 'seccio no acotada')\n"
 "  tipus: recte, reduccio, corba, pantaló, colector/plenum, injert, tapa, difusor, canvi de sentit...\n"
 "FASE 2 - LLISTA CSV amb capcalera: grup;codi;descr;w1;h1;w2;h2;uts;unit;preu;peces\n"
 "\n"
 "REGLES D'OR:\n"
 "- NO INVENTIS de cap manera. Pero SI tens dades reals, FES-LES SERVIR: combina els TRAMS MESURATS\n"
 "  (ample x llarg) amb les COTES del sistema per omplir les seccions dels conductes rectes i reduccions.\n"
 "  Exemple: si a RET hi ha trams de 800 d'ample i a les cotes hi ha 150 -> conducte 800x150.\n"
 "- Nomes deixa w1;h1;w2;h2 BUITS i '(seccio a confirmar)' quan NO tinguis ni mesura ni cota per deduir-la\n"
 "  (tipicament els fittings rars: pantaló, plenum, connexio, canvi de sentit, difusors).\n"
 "- Si DEDUEIXES alguna cosa raonable, marca-ho amb '(suposat)' al descr; aixi el tecnic ho revisa.\n"
 "- codis: rec, red, c90, c45, inj, des, tapa, tmalla, esp. pantaló/plenum/colector/connexio/canvi sentit = esp.\n"
 "- uts = el que factura VEGRA (metres si unit='m', quantitat si 'ut'). peces = peces fisiques reals (x1/x2; buit=1).\n"
 "- Cada reduccio es UNA peca de 1500 mm; NO multipliquis el llarg.\n"
 "- FORMAT ESTRICTE: cada fila CSV amb 10 punts i coma (11 camps). Mante els ';' encara que el camp quedi buit.\n"
 "  Exemple acotat:     IMP;c90;Corba 90 700x500;700;500;;;2;ut;;\n"
 "  Exemple SENSE cota: IMP;rec;Conducte (seccio a confirmar);;;;;;m;;\n"
 "- Respon NOMES amb les linies '# ' de l'inventari i despres el CSV. Cap explicacio extra."
)

def _img_block(path):
    data = base64.b64encode(open(path, "rb").read()).decode("ascii")
    mt = "image/png" if path.lower().endswith(".png") else "image/jpeg"
    return {"type": "image", "source": {"type": "base64", "media_type": mt, "data": data}}

def _cone_rows(cones):
    """Files CSV (red) del con, calculades de forma determinista des dels extrems reals."""
    rows = []
    for c in cones or []:
        s = c.get("system", ""); w = int(c.get("width", 0)); hs = c.get("heights", [])
        for i in range(len(hs) - 1):
            rows.append("%s;red;Con %dx%d-%dx%d (con estimat, ajustar);%d;%d;%d;%d;3;m;;"
                        % (s, w, hs[i], w, hs[i + 1], w, hs[i], w, hs[i + 1]))
    return rows

def _rule_accessories(text, cones):
    """Accessoris PER REGLA (no mesurats): a cada seccio de conducte li correspon una
       TAPA (final de ramal) i un INJERT (derivacio). Quantitat 1 -> Joan l'ajusta.
       No inventa mesures: fa servir les seccions que JA hi ha a la llista."""
    rec_sections = []          # [(sistema, w, h)] en ordre d'aparicio, sense repetir
    seen = set(); have = set()
    for ln in text.split("\n"):
        s = ln.strip()
        if not s or s.startswith("#") or s.startswith("grup;codi"):
            continue
        p = ln.split(";")
        if len(p) < 9:
            continue
        grp, codi = p[0].strip(), p[1].strip()
        try:
            w1 = int(float(p[3])) if p[3].strip() else 0
            h1 = int(float(p[4])) if p[4].strip() else 0
        except ValueError:
            continue
        if codi == "rec" and w1 > 0 and h1 > 0 and (grp, w1, h1) not in seen:
            seen.add((grp, w1, h1)); rec_sections.append((grp, w1, h1))
        if codi in ("tapa", "inj") and w1 > 0 and h1 > 0:
            have.add((grp, codi, w1, h1))
    rows = []
    for grp, w, h in rec_sections:
        if (grp, "tapa", w, h) not in have:
            rows.append("%s;tapa;Tapa %dx%d (per regla · ajustar qty);%d;%d;;;1;ut;;" % (grp, w, h, w, h))
        if (grp, "inj", w, h) not in have:
            rows.append("%s;inj;Injert %dx%d (per regla · ajustar qty);%d;%d;;;1;ut;;" % (grp, w, h, w, h))
    # tapa al final de cada con (seccio petita de sortida)
    for c in cones or []:
        grp = c.get("system", ""); w = int(c.get("width", 0)); h = int(c.get("heights", [0])[-1])
        if w > 0 and h > 0 and (grp, "tapa", w, h) not in have:
            rows.append("%s;tapa;Tapa %dx%d final con (per regla · ajustar qty);%d;%d;;;1;ut;;" % (grp, w, h, w, h))
    return rows

def build_pieces(a, images=None, model=None, timeout=180):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("Falta ANTHROPIC_API_KEY")
    model = model or os.environ.get("AI_MODEL", "claude-opus-4-8")
    cotas = ", ".join(str(c) for c in a.get("cotas", []))
    capas = "; ".join("%s (%s el.)" % (k, v) for k, v in a.get("cond_layers", {}).items()) or "(no detectades)"
    metres = "; ".join("%s = %s" % (k, v) for k, v in a.get("duct_len_m", {}).items()) or "(no mesurats)"
    by_sys = a.get("cotas_by_system") or {}
    runs = a.get("runs_by_system") or {}
    hts = a.get("heights_by_system") or {}
    dxf_block = ""
    if by_sys:
        linies = "\n".join("    %s: %s" % (s, ", ".join(str(c) for c in cs)) for s, cs in by_sys.items())
        dxf_block += ("- COTES REALS del DXF per sistema (FIABLES: objectes DIMENSION del plano):\n%s\n" % linies)
    if runs:
        rl = "\n".join("    %s: %s" % (s, "; ".join("%dx%d" % (w, l) for w, l in rr[:14]))
                       for s, rr in runs.items())
        dxf_block += ("- AMPLES x LLARGS mesurats de la geometria (planta, mm):\n%s\n" % rl)
    if hts:
        hl = "\n".join("    %s: %s" % (s, ", ".join(str(h) for h in hh)) for s, hh in hts.items())
        dxf_block += ("- ALTURES de seccio mesurades als ALÇATS (mm):\n%s\n" % hl)
    if runs or hts:
        dxf_block += ("  MUNTA cada conducte recte com AMPLE(mesurat) x ALTURA(mesurada a l'alçat del mateix sistema).\n"
                      "  Exemple RET: ample 800 + altura 150 -> 800x150 (NO 800x500). Tria l'altura mes coherent\n"
                      "  del seu sistema; son mesures reals, no les marquis '(a confirmar)' ni les inventis.\n")
    cones = a.get("cones") or []
    if cones:
        cl = "; ".join("%s (ample %d, de %d a %d)" % (c["system"], c["width"], c["heights"][0], c["heights"][-1])
                       for c in cones)
        dxf_block += ("- CON(S) DETECTAT(S): %s.\n"
                      "  Les reduccions del con les afegeixo JO automaticament. NO generis tu cap reduccio\n"
                      "  ni conducte per a aquest con; centra't en la RESTA (fittings, altres conductes, difusors).\n" % cl)
    txt = ("Dades llegides del plano:\n- Capes de conductes: %s\n"
           "- Longitud de linies per sistema (indicador aproximat, NO metres reals): %s\n"
           "%s"
           "- Cotes detectades per OCR (poden tenir errors; prioritza el DXF i la imatge): %s\n\n"
           % (capas, metres, dxf_block, cotas))
    if images:
        txt += ("Tens la/les pagina(es) i els seus quadrants ampliats. Recorre el pla accessori per "
                "accessori. ")
    txt += ("Fes FASE 1 (inventari '# ' amb les cotes ESCRITES) i FASE 2 (CSV). NO inventis cap mesura: "
            "el que no estigui acotat, marca'l '(seccio a confirmar)'. Retorna NOMES inventari + CSV.")
    content = [_img_block(p) for p in (images or [])]
    content.append({"type": "text", "text": txt})
    body = {"model": model, "max_tokens": 6000, "system": SYSTEM,
            "messages": [{"role": "user", "content": content}]}
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                 "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8"))
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    text = text.replace("```csv", "").replace("```", "").strip()
    if "grup;codi" not in text:
        text = "grup;codi;descr;w1;h1;w2;h2;uts;unit;preu;peces\n" + text
    # injectar les reduccions del con (calculades de forma determinista)
    crows = _cone_rows(cones)
    if crows:
        out = []; done = False
        for ln in text.split("\n"):
            out.append(ln)
            if not done and ln.strip().startswith("grup;codi"):
                out.extend(crows); done = True
        if not done:
            out = crows + out
        text = "\n".join(out)
    # accessoris PER REGLA (tapa + injert per seccio) al final, per revisar
    arows = _rule_accessories(text, cones)
    if arows:
        text = text.rstrip() + ("\n# --- accessoris proposats PER REGLA (ajusta la quantitat o esborra) ---\n"
                                + "\n".join(arows))
    via = "imatge+cotes" if images else "cotes"
    note = ("# Llista PRE-MUNTADA per IA (%s) - REVISA-LA abans de generar.\n"
            "# Les linies '#' son l'INVENTARI llegit del pla. Les peces amb '(seccio a confirmar)'\n"
            "# NO estaven acotades al pla: omple-les tu (no les ha inventat la IA).\n" % via)
    return note + text
