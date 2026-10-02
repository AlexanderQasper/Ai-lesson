FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg libgomp1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir torch==2.8.0 torchaudio==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir whisperx==3.8.6 && pip check
WORKDIR /processor
COPY run.py /processor/run.py
ENV HF_HOME=/cache/huggingface XDG_CACHE_HOME=/cache PYANNOTE_METRICS_ENABLED=0 OMP_NUM_THREADS=2 MKL_NUM_THREADS=2
ENTRYPOINT ["python", "-u", "/processor/run.py"]
