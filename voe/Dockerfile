# Voice of Emergence — thin Streamlit client over the E4 pilot API.
# Talks to the backend only over HTTP (VOICE_OF_EMERGENCE_API_BASE_URL);
# no secrets or backend URL are baked into this image.
FROM python:3.12-slim

WORKDIR /voe

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . ./

EXPOSE 8501

CMD ["streamlit", "run", "app.py", \
     "--server.address=0.0.0.0", "--server.port=8501", \
     "--server.headless=true", "--browser.gatherUsageStats=false", \
     "--client.showErrorDetails=none"]
