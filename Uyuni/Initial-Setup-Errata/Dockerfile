FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

RUN mkdir -p /var/log && touch /var/log/errata-manager.log

ENV FLASK_ENV=production

EXPOSE 5000

# Timeout 1800s per sync DSA (~63MB) e NVD batch lunghi
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "1800", "--graceful-timeout", "1800", "app:app"]
