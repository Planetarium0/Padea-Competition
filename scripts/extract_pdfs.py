import textwrap
import logging
from pathlib import Path

from pypdf import PdfReader

log = logging.getLogger("padea_migration")


def extract_as_text(pdf_path: Path, txt_path: Path) -> None:
    """Extract plain text from a PDF and write it to ``txt_path``.

    * ``pdf_path`` – path to the source PDF (must exist).
    * ``txt_path`` – destination ``.txt`` file. If the file already exists it will be overwritten.

    The function reads all pages with :class:`pypdf.PdfReader`, concatenates their
    text, then applies :func:`textwrap.dedent` to remove any leading indentation that
    may be introduced by block‑quote formatting in the original PDF.
    """
    if not isinstance(pdf_path, Path):
        pdf_path = Path(pdf_path)
    if not isinstance(txt_path, Path):
        txt_path = Path(txt_path)

    if not pdf_path.is_file():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    log.info("Extracting text from %s", pdf_path)
    reader = PdfReader(str(pdf_path))
    all_text = []
    for page_num, page in enumerate(reader.pages, start=1):
        try:
            page_text = page.extract_text() or ""
            all_text.append(page_text)
        except Exception as e:
            log.warning("Failed to extract text from page %d: %s", page_num, e)
    combined = "\n".join(all_text)
    # Remove common leading indentation (useful when PDFs contain block‑quote style text)
    cleaned = textwrap.dedent(combined).strip()
    txt_path.write_text(cleaned, encoding="utf-8")
    log.info("Written extracted text to %s (%.2f KiB)", txt_path, txt_path.stat().st_size / 1024)
