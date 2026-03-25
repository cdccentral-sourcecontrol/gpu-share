FROM nvidia/cuda:12.8.0-runtime-ubuntu24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN python3 -m venv /app/venv && /app/venv/bin/pip install --no-cache-dir -r requirements.txt pyyaml

COPY src/ /app/src/
COPY configs/config.example.yaml /app/configs/config.yaml

ENV PATH="/app/venv/bin:$PATH"
ENV PYTHONPATH="/app/src"

EXPOSE 8553
CMD ["python", "-m", "gpu_share.server"]
