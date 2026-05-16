# Skin AI needs native system libs (libxcb, libgl, glib) that the
# Railway Nixpacks base image doesn't include reliably. Switching to
# an explicit Dockerfile gets us deterministic apt installs.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Pre-set the DeepFace / TF env knobs that pipeline.py also sets,
    # so the values apply during model load even before Django imports
    # the pipeline module.
    TF_USE_LEGACY_KERAS=1 \
    TF_CPP_MIN_LOG_LEVEL=2 \
    TF_NUM_INTEROP_THREADS=1 \
    TF_NUM_INTRAOP_THREADS=1

# OpenCV native deps. DeepFace imports cv2 at package load, so the
# whole Skin AI chain dies without these on a slim base. Order:
#   libxcb1 / libxcb-shm0  → cv2 bootstrap
#   libgl1                 → cv2 image-IO GL paths
#   libglib2.0-0           → cv2 internal threading
#   libgomp1               → OpenMP runtime used by numpy + TF
#   libsm6 / libxext6 / libxrender1 → other X libs cv2 looks for
RUN apt-get update && apt-get install -y --no-install-recommends \
        libxcb1 libxcb-shm0 libgl1 libglib2.0-0 libgomp1 \
        libsm6 libxext6 libxrender1 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so the layer is cached across code-only
# pushes.
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/requirements.txt

# App source.
COPY . /app

# Whitenoise collects on boot via start.sh — same flow as the
# previous Nixpacks setup, just inside a known-good container.
EXPOSE 8080
CMD ["bash", "start.sh"]
