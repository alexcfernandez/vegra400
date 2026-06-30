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
 "- NO INVENTIS cap mesura. Una cota nomes hi va si esta ESCRITA al pla.\n"
 "- Si una seccio NO esta acotada, deixa w1;h1;w2;h2 BUITS i posa al descr '(seccio a confirmar)'.\n"
 "  El tecnic ho omplira; val mes buit i honest que un numero inventat.\n"
 "- Si DEDUEIXES alguna cosa (no esta escrita pero es evident), marca-ho amb '(suposat)' al descr.\n"
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

def build_pieces(a, images=None, model=None, timeout=180):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("Falta ANTHROPIC_API_KEY")
    model = model or os.environ.get("AI_MODEL", "claude-opus-4-8")
    cotas = ", ".join(str(c) for c in a.get("cotas", []))
    capas = "; ".join("%s (%s el.)" % (k, v) for k, v in a.get("cond_layers", {}).items()) or "(no detectades)"
    metres = "; ".join("%s = %s m" % (k, v) for k, v in a.get("duct_len_m", {}).items()) or "(no mesurats)"
    txt = ("Dades llegides del plano:\n- Capes de conductes: %s\n- Metres per capa: %s\n"
           "- Cotes detectades per OCR (poden tenir errors; PRIORITZA el que llegeixis a la imatge): %s\n\n"
           % (capas, metres, cotas))
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
    via = "imatge+cotes" if images else "cotes"
    note = ("# Llista PRE-MUNTADA per IA (%s) - REVISA-LA abans de generar.\n"
            "# Les linies '#' son l'INVENTARI llegit del pla. Les peces amb '(seccio a confirmar)'\n"
            "# NO estaven acotades al pla: omple-les tu (no les ha inventat la IA).\n" % via)
    return note + text
