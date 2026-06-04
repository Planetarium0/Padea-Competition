from __future__ import annotations

from pathlib import Path

import pypdf


def main() -> None:
    resources_dir = Path("resources")
    cache_dir = Path("cache")
    cache_dir.mkdir(exist_ok=True)

    pdfs = ["caterer-contacts.pdf", "caterer-menus.pdf", "exclusions.pdf", "absences.pdf"]
    for pdf in pdfs:
        pdf_path = resources_dir / pdf
        txt_path = cache_dir / pdf.replace(".pdf", ".txt")
        print(f"Extracting {pdf_path} to {txt_path}")
        reader = pypdf.PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
        txt_path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
