ARG PYTHON_IMAGE=python:3.13-slim
FROM ${PYTHON_IMAGE}

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY apps/vision_tools/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY apps/vision_tools/tpa_vision_tools /app/tpa_vision_tools

ENV PORT=8086
EXPOSE 8086

CMD ["sh", "-c", "uvicorn tpa_vision_tools.main:app --host 0.0.0.0 --port ${PORT}"]
