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

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Direct command - no entrypoint needed
CMD ["python", "-m", "uvicorn", "web_app:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "warning"]