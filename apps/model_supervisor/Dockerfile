ARG PYTHON_IMAGE=python:3.13-slim
FROM ${PYTHON_IMAGE}

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY apps/model_supervisor/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY apps/model_supervisor/tpa_model_supervisor /app/tpa_model_supervisor

EXPOSE 8091

CMD ["uvicorn", "tpa_model_supervisor.main:app", "--host", "0.0.0.0", "--port", "8091"]

