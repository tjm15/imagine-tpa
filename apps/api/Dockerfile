ARG PYTHON_IMAGE=python:3.13-slim
FROM ${PYTHON_IMAGE}

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY apps/api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# App code
COPY apps/api/tpa_api /app/tpa_api

# Spec pack (mounted in the same image so the API/UI can serve and validate against it)
COPY schemas /app/spec/schemas
COPY culp /app/spec/culp
COPY profiles /app/spec/profiles
COPY grammar /app/spec/grammar
COPY platform /app/spec/platform
COPY ingest /app/spec/ingest
COPY ux /app/spec/ux
COPY tests /app/spec/tests
COPY db /app/spec/db
COPY integration /app/spec/integration
COPY capabilities /app/spec/capabilities
COPY authorities /app/spec/authorities
COPY framing /app/spec/framing

EXPOSE 8000

CMD ["uvicorn", "tpa_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
