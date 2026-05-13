FROM python:3.11-slim

# Evita .pyc files y fuerza stdout/stderr sin buffer (logs en tiempo real)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Crea directorios necesarios y un placeholder vacío para Firebase.
# Si el usuario monta un firebase-credentials.json real vía docker-compose,
# ese archivo reemplaza este placeholder automáticamente.
RUN mkdir -p /app/data/videos && \
    echo '{}' > /app/firebase-credentials.json

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
