# Multi-stage build for find_good_hikes web application
FROM python:3.11-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Create and use non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set working directory
WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    sqlite3 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder and fix ownership
COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local

# Copy application code
COPY --chown=appuser:appuser . .

# Create required directories and copy existing databases
RUN mkdir -p /app/data /app/static /app/templates && \
    chown -R appuser:appuser /app

# Copy existing walk database to data directory if it exists
RUN if [ -f /app/walks.db ]; then cp /app/walks.db /app/data/walks.db; fi && \
    if [ -f /app/forecasts.sqlite.db ]; then cp /app/forecasts.sqlite.db /app/data/forecasts.sqlite.db; fi && \
    if [ -f /app/walkhighlands_cache.sqlite ]; then cp /app/walkhighlands_cache.sqlite /app/data/walkhighlands_cache.sqlite; fi && \
    if [ -f /app/met_weather_cache.sqlite ]; then cp /app/met_weather_cache.sqlite /app/data/met_weather_cache.sqlite; fi && \
    chown -R appuser:appuser /app/data

# Switch to non-root user
USER appuser

# Add local bin to PATH
ENV PATH=/home/appuser/.local/bin:$PATH

# Expose port
EXPOSE 8000

# Copy and set up entrypoint script
COPY --chown=appuser:appuser docker-entrypoint.sh /app/
RUN chmod +x /app/docker-entrypoint.sh

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health')" || exit 1

# Set entrypoint and default command
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "web_app:app", "--host", "0.0.0.0", "--port", "8000"]