"""
host_webapp.py — Serve the Padea webapp over the local network.

Binds to 0.0.0.0 so any device on the same Wi-Fi/LAN can reach it.

Usage:
    python scripts/actions/host_webapp.py [--port PORT]

After starting, generate matching QR codes with:
    ./run qr --origin http://<printed-ip>:<port>
"""

import argparse
import os
import socket
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

WEBAPP_DIR = Path("webapp")
DEFAULT_PORT = 8000


def local_ip():
    """Best-guess LAN IP by connecting a UDP socket (never actually sends)."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return "localhost"


def main(port=DEFAULT_PORT):
    os.chdir(WEBAPP_DIR)

    ip = local_ip()
    origin = f"http://{ip}:{port}"

    print(f"Serving:  {WEBAPP_DIR}")
    print(f"Local:    http://localhost:{port}/index.html")
    print(f"Network:  {origin}/index.html")
    print()
    print(f"Generate QR codes for this server:")
    print(f"  ./run qr --origin {origin}")
    print()
    print("Press Ctrl+C to stop.")
    print()

    server = HTTPServer(("0.0.0.0", port), SimpleHTTPRequestHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Serve the Padea webapp on the local network")
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT,
        help=f"Port to listen on (default: {DEFAULT_PORT})",
    )
    args = parser.parse_args()
    main(port=args.port)
