# Sous on Cloud Run GPU (NVIDIA L4) with cuDF / RAPIDS.
# To deploy: back up your CPU Dockerfile, copy this one to "Dockerfile", then
# run the --gpu deploy command (see DEPLOY.md / the chat). SOUS_USE_GPU=1 turns
# on the live cuDF benchmark in sous_core.py.
FROM nvidia/cuda:12.4.1-runtime-ubuntu22.04
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements-gpu.txt .
RUN pip3 install --extra-index-url=https://pypi.nvidia.com -r requirements-gpu.txt
COPY .streamlit/ ./.streamlit/
COPY static/ ./static/
COPY sous_core.py app.py ./
RUN useradd --create-home sous && chown -R sous /app
USER sous
ENV PORT=8080 SOUS_USE_GPU=1
EXPOSE 8080
CMD streamlit run app.py --server.port=${PORT} --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false
