FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py ./app.py
COPY p3_patch_testing.py ./p3_patch_testing.py

# Environment variables (defaults, override at runtime)
ENV FLASK_ENV=production

# Expose port
EXPOSE 5000

# Run with gunicorn for production
# Timeout 1800s (30 min) for long-running sync operations (NVD, OVAL)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "1800", "--graceful-timeout", "1800", "app:app"]
