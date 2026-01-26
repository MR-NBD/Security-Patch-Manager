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
COPY app-v2.5-IMPROVED.py ./app.py
COPY p3_patch_testing.py ./p3_patch_testing.py

# Create directory for SQL files
COPY sql/ ./sql/

# Environment variables (defaults, override at runtime)
ENV FLASK_ENV=production
ENV DB_HOST=localhost
ENV DB_PORT=5432
ENV DB_NAME=errata_db
ENV DB_USER=errata_user
ENV DB_PASSWORD=changeme
ENV UYUNI_HOST=
ENV UYUNI_USER=
ENV UYUNI_PASSWORD=

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

# Run with gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "app:app"]
