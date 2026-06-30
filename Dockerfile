FROM python:3.12-slim
# tesseract para el OCR de los planos PDF
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr && rm -rf /var/lib/apt/lists/*
ENV MPLCONFIGDIR=/tmp/mpl PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Railway define $PORT; gunicorn sirve la app
CMD ["sh","-c","gunicorn -b 0.0.0.0:${PORT:-5000} --timeout 180 app:app"]
