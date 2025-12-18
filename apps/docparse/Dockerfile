ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Docling can require common system libraries depending on enabled backends.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
      libglib2.0-0 \
      libgl1 \
      poppler-utils \
      tesseract-ocr \
    ; \
    rm -rf /var/lib/apt/lists/*

COPY apps/docparse/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY apps/docparse/tpa_docparse /app/tpa_docparse

EXPOSE 8084

CMD ["uvicorn", "tpa_docparse.main:app", "--host", "0.0.0.0", "--port", "8084"]

