FROM python:3.11-slim

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Create cache directory with proper permissions
RUN mkdir -p /app/cache && chown appuser:appuser /app/cache

# Switch to non-root user
USER appuser

# Expose port for health checks
EXPOSE 8000

# Run the MCP server
CMD ["python", "server.py"]