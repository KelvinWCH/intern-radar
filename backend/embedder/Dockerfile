# optional gpu sidecar for nvidia jetson boards (jetpack 6, cuda 12.6)
# the cuda libs are mounted from the host by compose.gpu.yaml
FROM python:3.10-slim-bookworm

ARG ONNXRUNTIME_GPU_VERSION=1.24.0
RUN pip install --no-cache-dir \
        --index-url https://pypi.jetson-ai-lab.io/jp6/cu126/+simple \
        --extra-index-url https://pypi.org/simple \
        "onnxruntime-gpu==${ONNXRUNTIME_GPU_VERSION}" "tokenizers>=0.20,<1" "numpy>=1.26,<3" \
    && groupadd --gid 10001 embedder \
    && useradd --uid 10001 --gid embedder --no-create-home embedder

WORKDIR /app
# same encoder as the worker so cpu and gpu vectors match
COPY src/job_backend/matching/onnx_model.py ./onnx_model.py
RUN python -c "from pathlib import Path; from onnx_model import download_model; download_model(Path('/models'))" \
    && chmod -R a+rX /models
COPY embedder/server.py embedder/model_process.py ./

ENV NVIDIA_VISIBLE_DEVICES=all \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility \
    LD_LIBRARY_PATH=/opt/nvidia/cuda:/opt/nvidia/lib \
    EMBEDDER_MODEL_DIR=/models \
    PYTHONUNBUFFERED=1
USER embedder
EXPOSE 8100
ENTRYPOINT ["python", "server.py"]
