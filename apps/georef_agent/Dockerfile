ARG PYTHON_IMAGE=python:3.12-slim
FROM ${PYTHON_IMAGE}

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY apps/georef_agent/requirements.txt /app/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends \
    gdal-bin \
    libgdal-dev \
    tesseract-ocr \
  && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY apps/georef_agent/tpa_georef_agent /app/tpa_georef_agent

EXPOSE 8090

CMD ["uvicorn", "tpa_georef_agent.main:app", "--host", "0.0.0.0", "--port", "8090"]
