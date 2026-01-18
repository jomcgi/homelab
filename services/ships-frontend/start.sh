#!/bin/sh
set -e

echo "Building ships-frontend..."

# Build the Vite app
cd /app/website
bun install
bun run build

# Move built files to public directory
mv dist/* /app/public/

# Start the server
cd /app
echo "Starting Bun server..."
exec bun run /app/server.ts
