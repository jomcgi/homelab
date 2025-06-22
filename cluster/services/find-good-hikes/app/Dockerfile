# Single-stage build with baked-in data
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and existing databases
COPY --chown=appuser:appuser . .

# Create data directory and ensure all files are owned by appuser
RUN mkdir -p /app/data && \
    chown -R appuser:appuser /app

# Update weather forecasts during build (now with fixed SQLite concurrency)
RUN python main.py fetch-weather || echo "Weather update failed, continuing with existing data"

# Create startup script to copy databases to writable location
RUN echo '#!/bin/bash\n\
# Copy pre-built databases to DATA_DIR if they exist\n\
if [ -f /app/walks.db ] && [ ! -f ${DATA_DIR}/walks.db ]; then\n\
    cp /app/walks.db ${DATA_DIR}/walks.db\n\
fi\n\
if [ -f /app/forecasts.sqlite.db ] && [ ! -f ${DATA_DIR}/forecasts.sqlite.db ]; then\n\
    cp /app/forecasts.sqlite.db ${DATA_DIR}/forecasts.sqlite.db\n\
fi\n\
# Start the application\n\
exec python -m uvicorn web_app:app --host 0.0.0.0 --port 8000 --log-level warning\n\
' > /app/start.sh && chmod +x /app/start.sh

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Use startup script
CMD ["/app/start.sh"]