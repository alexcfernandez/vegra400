# -*- coding: utf-8 -*-
"""Capa de IA (bajo coste) que monta la lista de piezas a partir de lo leido del DXF.
Usa la API de Anthropic (modelo economico) con la clave en la variable ANTHROPIC_API_KEY.
Si no hay clave o falla, lanza excepcion y la app cae al modo manual (scaffold)."""
import os, json, urllib.request

SYSTEM = (
 "Ets un tecnic expert en fabricacio de conductes metallics rectangulars (estil VEGRA 400).\n"
 "A partir de les dades llegides d'un plano (cotes i capes), has de muntar la LLISTA DE PECES per a taller.\n"
 "REGLES:\n"
 "- Sortida NOMES en CSV amb capcalera: grup;codi;descr;w1;h1;w2;h2;uts;unit;preu\n"
 "- codis: rec (conducte recte), red (reduccio/transformacio), c90 (corba 90), c45 (corba 45),\n"
 "  inj (injert), des (desviament), tapa (tapa), tmalla (tapa malla), esp (peca especial).\n"
 "- grup: nom de la partida (ex: '1.1 INTERIOR - IMPULSIO').\n"
 "- w1;h1 = seccio d'entrada (mm); w2;h2 = seccio de sortida (mm) nomes en reduccions (red), si no deixa-les igual.\n"
 "- uts = metres lineals si unit='m' (conductes), o quantitat si unit='ut' (tapes, corbes, accessoris).\n"
 "- TROCEJAT maxim 1500 mm per tram: si un conducte fa mes, parteix-lo en trams.\n"
 "- Si un tronc va d'una seccio gran a una de petita (con), reparteix l'alcada en trams de 1500 mm,\n"
 "  interpolant linealment l'alcada entre l'inici i el final (com fa el tecnic a ma).\n"
 "- Unions per defecte M20 als dos extrems; tapes als finals de ramal.\n"
 "- preu nomes per a peces especials (esp) o ma d'obra; la resta deixa preu buit.\n"
 "- NO escriguis cap explicacio, NOMES les linies CSV."
)

def build_pieces(a, model=None, timeout=90):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("Falta ANTHROPIC_API_KEY")
    model = model or os.environ.get("AI_MODEL", "claude-3-5-haiku-latest")
    cotas = ", ".join(str(c) for c in a.get("cotas", []))
    capas = "; ".join("%s (%s el.)" % (k, v) for k, v in a.get("cond_layers", {}).items()) or "(no detectades pel nom)"
    metres = "; ".join("%s = %s m" % (k, v) for k, v in a.get("duct_len_m", {}).items()) or "(no mesurats)"
    user = (
        "Dades llegides del DXF:\n"
        "- Capes de conductes: %s\n"
        "- Metres per capa: %s\n"
        "- Cotes detectades (mm): %s\n\n"
        "Munta la llista de peces el mes fidel possible. Retorna NOMES el CSV." % (capas, metres, cotas)
    )
    body = {"model": model, "max_tokens": 3000, "system": SYSTEM,
            "messages": [{"role": "user", "content": user}]}
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
    # marca informativa al principi
    header = "# Llista PRE-MUNTADA per IA a partir del plano - REVISA-LA abans de generar\n"
    lines = text.split("\n")
    return lines[0] + "\n" + header + "\n".join(lines[1:])
