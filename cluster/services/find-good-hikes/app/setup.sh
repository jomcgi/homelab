#!/bin/bash
# Setup script for find_good_hikes project

set -e

echo "Setting up find_good_hikes virtual environment..."

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

echo "Setup complete!"
echo ""
echo "To use the project:"
echo "1. Activate the virtual environment: source venv/bin/activate"
echo "2. Run commands: python main.py --help"
echo ""
echo "Quick start:"
echo "  python main.py update      # Scrape walks and fetch weather"
echo "  python main.py find 55.8827 -4.2589  # Find walks near Glasgow"