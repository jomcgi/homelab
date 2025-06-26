#!/usr/bin/env python3
"""Simple HTTP server for testing the Find Good Hikes static site locally."""

import http.server
import socketserver
import os

# Change to the public directory
os.chdir('public')

# Define the server
PORT = 8000
Handler = http.server.SimpleHTTPRequestHandler

# Add CORS headers for R2 access
class CORSRequestHandler(Handler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

# Start the server
with socketserver.TCPServer(("", PORT), CORSRequestHandler) as httpd:
    print(f"Server running at http://localhost:{PORT}/")
    print("Press Ctrl+C to stop the server")
    httpd.serve_forever()