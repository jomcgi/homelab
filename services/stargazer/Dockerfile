FROM python:3.11-alpine

# Install runtime dependencies
RUN apk add --no-cache \
    gcc \
    musl-dev \
    python3-dev \
    libffi-dev \
    openssl-dev

# Set working directory
WORKDIR /app

# Copy requirements if they exist, otherwise install common packages
RUN pip install --no-cache-dir \
    requests \
    numpy \
    scipy \
    pandas \
    python-dateutil \
    pytz

# Copy the entire services directory to maintain module structure
COPY services/ /app/services/

# Create data directory
RUN mkdir -p /data/output

# Set the module path
ENV PYTHONPATH=/app

# Default command
CMD ["python3", "-m", "services.stargazer.app.main"]