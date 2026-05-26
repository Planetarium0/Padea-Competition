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

from __future__ import annotations

import argparse
import json
import re
import socket
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from support import Database
from actions.api import api_approve_proposal, api_get_proposal, api_reject_proposal

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEBAPP_DIR = PROJECT_ROOT / "webapp"
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_PORT = 8000

_RE_PROPOSAL = re.compile(r"^/api/proposal/([^/?]+)$")
_RE_APPROVE  = re.compile(r"^/api/proposal/([^/?]+)/approve$")
_RE_REJECT   = re.compile(r"^/api/proposal/([^/?]+)/reject$")


def local_ip() -> str:
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
    """Serves static webapp files and handles /api/proposal/* routes."""

    # ------------------------------------------------------------------
    # API routing
    # ------------------------------------------------------------------

    def do_GET(self) -> None:
        bare = self.path.split("?", 1)[0]
        m = _RE_PROPOSAL.match(bare)
        if m:
            status, body = api_get_proposal(m.group(1), Database.from_env())
            self._send_json(status, body)
            return
        super().do_GET()

    def do_POST(self) -> None:
        bare = self.path.split("?", 1)[0]
        m = _RE_APPROVE.match(bare)
        if m:
            status, body = api_approve_proposal(m.group(1), Database.from_env())
            self._send_json(status, body)
            return
        m = _RE_REJECT.match(bare)
        if m:
            length = int(self.headers.get("Content-Length", 0))
            data   = json.loads(self.rfile.read(length)) if length else {}
            notes  = data.get("notes", "") if isinstance(data, dict) else ""
            status, body = api_reject_proposal(m.group(1), notes, Database.from_env())
            self._send_json(status, body)
            return
        self._send_json(404, {"error": "Not found"})

    def _send_json(self, status: int, body: dict) -> None:
        encoded = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    # ------------------------------------------------------------------
    # Static file routing
    # ------------------------------------------------------------------

    def translate_path(self, path: str) -> str:
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


def main(port: int = DEFAULT_PORT) -> None:
    ip = local_ip()
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
