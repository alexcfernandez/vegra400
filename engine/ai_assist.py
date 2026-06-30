# -*- coding: utf-8 -*-
"""Capa de IA (Anthropic) que monta la lista de piezas a partir de lo leido del DXF
y, si hi ha, d'una IMATGE del plano (visio). Clau a ANTHROPIC_API_KEY, model a AI_MODEL.
Si no hi ha clau o falla, llanca excepcio i l'app cau al mode manual."""
import os, json, base64, urllib.request

SYSTEM = (
 "Ets un tecnic expert en fabricacio de conductes metallics rectangulars (estil VEGRA 400).\n"
 "Munta la LLISTA DE PECES per a taller a partir del plano (imatge si n'hi ha) i les cotes.\n"
 "REGLES:\n"
 "- Sortida NOMES en CSV amb capcalera: grup;codi;descr;w1;h1;w2;h2;uts;unit;preu\n"
 "- codis: rec (recte), red (reduccio), c90 (corba 90), c45 (corba 45), inj (injert),\n"
 "  des (desviament), tapa, tmalla (tapa malla), esp (especial).\n"
 "- grup: nom de la partida. w1;h1 entrada (mm); w2;h2 sortida (mm) nomes en reduccions.\n"
 "- uts = metres lineals si unit='m' (conductes), o quantitat si unit='ut'.\n"
 "- TROCEJAT maxim 1500 mm per tram.\n"
 "- En troncs que es redueixen (con), reparteix l'alcada en trams de 1500 mm interpolant.\n"
 "- Unions M20 per defecte; tapes als finals de ramal. preu nomes per a especials/ma d'obra.\n"
 "- Si NO estas segur d'una mesura, fes la millor estimacio pero NO inventis seccions que no es dedueixin del plano.\n"
 "- Respon NOMES amb les linies CSV, sense cap explicacio."
)

def _img_block(path):
    data = base64.b64encode(open(path, "rb").read()).decode("ascii")
    mt = "image/png" if path.lower().endswith(".png") else "image/jpeg"
    return {"type": "image", "source": {"type": "base64", "media_type": mt, "data": data}}

def build_pieces(a, images=None, model=None, timeout=120):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("Falta ANTHROPIC_API_KEY")
    model = model or os.environ.get("AI_MODEL", "claude-opus-4-8")
    cotas = ", ".join(str(c) for c in a.get("cotas", []))
    capas = "; ".join("%s (%s el.)" % (k, v) for k, v in a.get("cond_layers", {}).items()) or "(no detectades)"
    metres = "; ".join("%s = %s m" % (k, v) for k, v in a.get("duct_len_m", {}).items()) or "(no mesurats)"
    txt = ("Dades llegides del plano:\n- Capes de conductes: %s\n- Metres per capa: %s\n"
           "- Cotes (mm): %s\n\n" % (capas, metres, cotas))
    if images:
        txt += "Tens tambe la/les imatge(s) del plano: llegeix-les per treure seccions, trazat i longituds. "
    txt += "Munta la llista de peces el mes fidel possible. Retorna NOMES el CSV."
    content = [_img_block(p) for p in (images or [])]
    content.append({"type": "text", "text": txt})
    body = {"model": model, "max_tokens": 4000, "system": SYSTEM,
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
        text = "grup;codi;descr;w1;h1;w2;h2;uts;unit;preu\n" + text
    via = "imatge+cotes" if images else "cotes"
    header = "# Llista PRE-MUNTADA per IA (%s) - REVISA-LA abans de generar\n" % via
    lines = text.split("\n")
    return lines[0] + "\n" + header + "\n".join(lines[1:])
