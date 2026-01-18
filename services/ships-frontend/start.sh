#!/bin/sh
set -e

echo "Building ships-frontend..."

# Build the Vite app (path matches Bazel package structure)
cd /app/website/websites/ships.jomcgi.dev
bun install
bun run build

# Move built files to public directory
mv dist/* /app/public/

# Start the server
cd /app
echo "Starting Bun server..."
exec bun run /app/server.ts
