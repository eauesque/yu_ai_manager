# YU AI Manager -- Production Dockerfile
# Build context: project root (..)

FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application source
COPY . .

# Non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Data directory (for volume mounting)
RUN mkdir -p /app/data && chown -R appuser:appuser /app/data

USER appuser

EXPOSE 5000

CMD ["python", "web_ui.py", "--db", "/app/data/tags.db", "--host", "0.0.0.0", "--port", "5000"]
