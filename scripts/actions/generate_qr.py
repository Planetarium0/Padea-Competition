"""
generate_qr.py — Generate QR code PNGs for each session's web app URL.

Each QR code encodes:
  file:///path/to/output/webapp/index.html?session=<airtable_record_id>

Or, if --base-url is supplied:
  <base-url>?session=<airtable_record_id>

Output: output/qrcodes/<session_id>.png

Usage:
  python scripts/generate_qr.py [--base-url URL] [--session SESSION_ID]
"""

import os
import sys
import argparse
from pathlib import Path
import support as s

try:
    import qrcode
    from qrcode.image.styledpil import StyledPilImage
    from qrcode.image.styles.moduledrawers.pil import RoundedModuleDrawer
    STYLED = True
except ImportError:
    import qrcode
    STYLED = False

OUTPUT_DIR = Path.cwd() / "output" / "qrcodes"
WEBAPP_PATH = Path.cwd() / "webapp" / "index.html"


def make_session_url(session_id, base_url=None):
    if base_url:
        return f"{base_url.rstrip('/')}?session={session_id}"
    # Local file URL
    abs_path = WEBAPP_PATH.resolve()
    return f"file://{abs_path}?session={session_id}"


def generate_qr(url, output_path):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=12,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)

    if STYLED:
        img = qr.make_image(
            image_factory=StyledPilImage,
            module_drawer=RoundedModuleDrawer(),
        )
    else:
        img = qr.make_image(fill_color="black", back_color="white")

    img.save(output_path)
    s.log.info(f"  QR saved: {output_path}")


def main(base_url=None, filter_session=None):
    sessions = s.airtable_get("Sessions")

    if not sessions:
        s.log.warning("No sessions found in Airtable.")
        return

    if filter_session:
        sessions = [sess for sess in sessions if sess["id"] == filter_session
                    or sess["fields"].get("Session ID") == filter_session]
        if not sessions:
            s.log.error(f"Session '{filter_session}' not found.")
            return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    s.log.info(f"Generating QR codes for {len(sessions)} session(s) → {OUTPUT_DIR}")

    for sess in sessions:
        sess_id = sess["id"]
        sess_label = sess["fields"].get("Session ID", sess_id)

        url = make_session_url(sess_id, base_url)
        safe_name = sess_label.replace(" ", "_").replace("/", "-")
        out_path = OUTPUT_DIR / f"{safe_name}.png"

        s.log.info(f"Session: {sess_label}")
        s.log.info(f"  URL: {url}")
        generate_qr(url, out_path)

    s.log.info(f"\nDone. {len(sessions)} QR code(s) written to {OUTPUT_DIR}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate session QR codes")
    parser.add_argument(
        "--base-url",
        help="Base URL for the web app (default: local file:// path)",
        default=None,
    )
    parser.add_argument(
        "--session",
        help="Only generate QR for this session ID or record ID",
        default=None,
    )
    args = parser.parse_args()

    main(base_url=args.base_url, filter_session=args.session)
