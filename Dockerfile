# Sous - Streamlit on Cloud Run
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY .streamlit/ ./.streamlit/
COPY static/ ./static/
COPY sous_core.py app.py ./

# Run as a non-root user (Cloud Run best practice).
RUN useradd --create-home sous && chown -R sous /app
USER sous

# Cloud Run provides $PORT (default 8080). Streamlit must bind to it, headless.
ENV PORT=8080
EXPOSE 8080
CMD streamlit run app.py --server.port=${PORT} --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false
