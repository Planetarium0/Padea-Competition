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
import io
import json
import re
import socket
import urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

try:
    import qrcode
    from qrcode.image.styledpil import StyledPilImage
    from qrcode.image.styles.moduledrawers.pil import RoundedModuleDrawer
    _QR_STYLED = True
except ImportError:
    try:
        import qrcode  # type: ignore[no-redef]
        _QR_STYLED = False
    except ImportError:
        qrcode = None  # type: ignore[assignment]
        _QR_STYLED = False

from support import Database
from actions.api import _routes, dispatch

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WEBAPP_DIR = PROJECT_ROOT / "webapp"
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_PORT = 8000



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
        m = re.match(r"^/qr/([^/?]+)$", bare)
        if m:
            self._handle_qr(m.group(1))
            return
        if not self._dispatch("GET"):
            super().do_GET()

    def do_POST(self) -> None:
        if not self._dispatch("POST"):
            self._send_json(404, {"error": "Not found"})

    def do_PATCH(self) -> None:
        if not self._dispatch("PATCH"):
            self._send_json(404, {"error": "Not found"})

    def _handle_qr(self, session_id: str) -> None:
        if qrcode is None:
            self._send_json(500, {"error": "qrcode library not installed"})
            return
        host = self.headers.get("Host", "localhost")
        url = f"http://{host}/meals.html?session={session_id}"
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=12,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        if _QR_STYLED:
            img = qr.make_image(
                image_factory=StyledPilImage,
                module_drawer=RoundedModuleDrawer(),
            )
        else:
            img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(png_bytes)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self.end_headers()
        self.wfile.write(png_bytes)

    def _dispatch(self, method: str) -> bool:
        bare = self.path.split("?", 1)[0]
        payload = self._read_payload(method)
        db = Database.from_env()
        for verb, pattern, handler in _routes:
            if verb == method and (m := pattern.match(bare)):
                self._send_json(*dispatch(handler, m, payload, db))
                return True
        return False

    def _read_payload(self, method: str) -> dict:
        if method == "GET":
            qs = self.path.split("?", 1)[1] if "?" in self.path else ""
            return {k: v[0] for k, v in urllib.parse.parse_qs(qs).items()}
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

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

    server = ThreadingHTTPServer(("0.0.0.0", port), PadeaHandler)
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
