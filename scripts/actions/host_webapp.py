"""
host_webapp.py — Serve the Padea webapp over the local network.

Binds to 0.0.0.0 so any device on the same Wi-Fi/LAN can reach it.

Routes:
  /            -> webapp/index.html
  /<path>      -> webapp/<path>     (HTML, JS, CSS, assets)
  /data/<file> -> data/<file>       (shared JSON files, e.g. dietary_keywords)

Anything else is rejected — the rest of the project (resources/, scripts/,
.env, …) is intentionally not exposed.

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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEBAPP_DIR   = PROJECT_ROOT / "webapp"
DATA_DIR     = PROJECT_ROOT / "data"
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


class PadeaHandler(SimpleHTTPRequestHandler):
    """Maps URL prefixes to two whitelisted directories on disk."""

    def translate_path(self, path):
        # Strip query string + normalise (parent does this, but we want the
        # path relative to *our* roots, not cwd).
        path = path.split("?", 1)[0].split("#", 1)[0]
        # Collapse '..' segments safely.
        parts = [p for p in path.split("/") if p and p != "."]
        if any(p == ".." for p in parts):
            # Refuse traversal — parent's translate_path also strips these,
            # but be explicit so the intent is obvious.
            return str(WEBAPP_DIR)  # will 404 at the file-system layer
        if parts and parts[0] == "data":
            return str(DATA_DIR.joinpath(*parts[1:]))
        return str(WEBAPP_DIR.joinpath(*parts))


def main(port=DEFAULT_PORT):
    ip     = local_ip()
    origin = f"http://{ip}:{port}"

    print(f"Webapp:   {WEBAPP_DIR}")
    print(f"Data:     {DATA_DIR} (served at /data/)")
    print(f"Local:    http://localhost:{port}/index.html")
    print(f"Network:  {origin}/index.html")
    print()
    print(f"Generate QR codes for this server:")
    print(f"  ./run qr --origin {origin}")
    print()
    print("Press Ctrl+C to stop.")
    print()

    server = HTTPServer(("0.0.0.0", port), PadeaHandler)
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
