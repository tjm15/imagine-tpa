# Use PyTorch with CUDA support for SAM2
ARG PYTHON_IMAGE=pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime
FROM ${PYTHON_IMAGE}

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TORCH_CUDNN_V8_API_ENABLED=1

# Install system dependencies for SAM2 and OpenCV
RUN apt-get update && apt-get install -y \
    git \
    wget \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsndfile1 \
    ffmpeg \
    libsm6 \
    libxext6 \
    && rm -rf /var/lib/apt/lists/*

COPY apps/vision_tools/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Clone and install SAM2
# We install from the official repo.
# Note: In production, pin this to a specific commit.
RUN git clone https://github.com/facebookresearch/segment-anything-2.git /app/sam2 && \
    cd /app/sam2 && \
    pip install -e .

# Create checkpoints directory
RUN mkdir -p /app/checkpoints

# Download SAM2 Hiera Large weights
# Using the URL from the official repo's README/setup script
RUN wget -O /app/checkpoints/sam2_hiera_large.pt https://dl.fbaipublicfiles.com/segment_anything_2/072824/sam2_hiera_large.pt

COPY apps/vision_tools/tpa_vision_tools /app/tpa_vision_tools

ENV PORT=8086
EXPOSE 8086

CMD ["sh", "-c", "uvicorn tpa_vision_tools.main:app --host 0.0.0.0 --port ${PORT}"]