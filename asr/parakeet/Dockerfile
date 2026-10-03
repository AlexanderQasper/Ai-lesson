FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgomp1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir 'onnx-asr[cpu,hub]' && pip check
ENV HF_HOME=/cache/huggingface HF_HUB_DISABLE_TELEMETRY=1 OMP_NUM_THREADS=2
WORKDIR /processor
COPY run.py /processor/run.py
ENTRYPOINT ["python", "-u", "/processor/run.py"]
