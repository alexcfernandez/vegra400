# Despiece & Pressupost — v1 (Assecador)

App web: subes el plano del proyecto y devuelve **3 archivos**:
1. **Presupuesto** (Excel) con la tarifa de VEGRA reconstruida (material por fórmula + mano de obra), separado por partidas.
2. **Planos de taller** (PDF) con cotas y desarrollo de chapa.
3. **Archivo CNC** (DXF) con los blanks de corte.

## Cómo funciona el flujo
`Subir plano (PDF/DXF)` → `Revisar/editar la lista de piezas` → `Generar y descargar`

- **PDF**: las cotas se leen por OCR (aproximado). La lista sale pre-rellenada **para revisar** antes de generar. Pensado como herramienta de revisión del precio.
- **DXF**: lectura vectorial limpia (cotas y conductos como objetos). El lector se calibra con un DXF real del arquitecto — pendiente de recibir una muestra.

## Ejecutar en local
Requisitos del sistema: Python 3.10+ y **tesseract-ocr**.
```bash
# Ubuntu/Debian:  sudo apt-get install -y tesseract-ocr
# macOS (brew):   brew install tesseract
pip install -r requirements.txt
python app.py
# abrir http://localhost:5000
```
Para probar sin plano: en la página de inicio, "Usar exemple" carga la obra del assecador.

## Desplegar para enviar un enlace a Joan (GitHub + Railway)
Railway construye la imagen Docker incluida (con tesseract) y te da una URL pública.

1. **GitHub**: crea un repo nuevo y sube esta carpeta `app/`:
   ```bash
   cd app
   git init && git add . && git commit -m "v1 despiece + pressupost"
   git branch -M main
   git remote add origin https://github.com/USUARIO/REPO.git
   git push -u origin main
   ```
2. **Railway**: New Project → *Deploy from GitHub repo* → elige el repo.
   - Railway detecta el `Dockerfile` y construye solo. No hay que configurar nada más.
   - Cuando termine: pestaña *Settings → Networking → Generate Domain*. Eso te da la URL pública (`https://....up.railway.app`) para enviar a Joan.
3. Joan abre la URL, prueba con "Usar exemple" o sube un plano, y descarga el presupuesto + planos + DXF.

**SiteGround**: no es adecuado para esto (es hosting compartido tipo WordPress/PHP; no corre un servicio Python con tesseract). Úsalo para web/dominio, pero el sistema va en Railway.

## Estructura
```
app.py                 # web (subir/revisar/generar/descargar)
pipeline.py            # orquestador: lista revisada -> 3 entregables
engine/precios.py      # tarifa VEGRA + generador de presupuesto (Excel)
engine/despiece.py     # desarrollo de chapa: planos de taller (PDF) + DXF
engine/extract.py      # OCR de cotas del PDF (pendiente: lector DXF)
sample_assecador.csv   # lista de ejemplo (= reproduce la oferta V-26143)
```

## Estado / alcance v1 (honesto)
- ✅ Presupuesto: reproduce la oferta V-26143 con <0,1% de desviación. Tarifa editable (hoja `Tarifa`).
- ✅ Planos de taller + DXF: para conductes rectos, reduccions (aprox.) y tapes, con troceado a 1500 mm y costura Pittsburgh (35/10).
- ⏳ Por hacer: lector DXF real; módulos de accesorios (corba, pantaló, injert, desviament) para planos/DXF; reglas de precio de piezas especiales y de mano de obra (hoy son entrada manual).
