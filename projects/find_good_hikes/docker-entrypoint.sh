#!/bin/bash
set -e

# Check if walks database exists
if [ ! -f "/app/walks.db" ] && [ ! -f "/app/data/walks.db" ]; then
    echo "No walks database found. Please run initial data setup:"
    echo "kubectl apply -f /path/to/init-job.yaml"
    echo "Starting web server without data..."
else
    echo "Walks database found."
    
    # Check if forecasts database exists and is recent (less than 6 hours old)
    FORECAST_DB="/app/forecasts.sqlite.db"
    DATA_FORECAST_DB="/app/data/forecasts.sqlite.db"
    
    if [ -f "$FORECAST_DB" ]; then
        FORECAST_FILE="$FORECAST_DB"
    elif [ -f "$DATA_FORECAST_DB" ]; then
        FORECAST_FILE="$DATA_FORECAST_DB"
    else
        FORECAST_FILE=""
    fi
    
    if [ -z "$FORECAST_FILE" ] || [ $(find "$FORECAST_FILE" -mmin +360 2>/dev/null | wc -l) -eq 1 ]; then
        echo "Weather data is missing or stale, updating forecasts..."
        python main.py fetch-weather || echo "Weather update failed, continuing with existing data"
    else
        echo "Weather data is current."
    fi
fi

echo "Starting find-good-hikes web application..."
exec "$@"