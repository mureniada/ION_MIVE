# Streamlit thin-client UI. Talks to the backend only over HTTP (BACKEND_URL).
FROM python:3.12-slim

WORKDIR /ui

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

EXPOSE 8501

# Local browser only; headless server mode, no telemetry.
CMD ["streamlit", "run", "streamlit_app.py", \
     "--server.address=0.0.0.0", "--server.port=8501", \
     "--server.headless=true", "--browser.gatherUsageStats=false"]
