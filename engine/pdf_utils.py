"""Safe extraction of answer text from small PDFs and text files."""
from __future__ import annotations
import io
import re

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_PDF_PAGES = 40
MAX_EXTRACTED_CHARS = 60_000


class ExtractionError(Exception):
    pass


def _normalise(text: str) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"-\n(?=[a-z])", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()
    if len(text) > MAX_EXTRACTED_CHARS:
        raise ExtractionError(f"Extracted text exceeds the {MAX_EXTRACTED_CHARS:,}-character limit.")
    return text


def extract_text(file_bytes: bytes, filename: str) -> str:
    """Extract selectable text only; limit bytes, pages and text to constrain resource use."""
    if not isinstance(file_bytes, (bytes, bytearray)):
        raise ExtractionError("The uploaded file could not be read.")
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        raise ExtractionError(f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit.")
    name = str(filename or "").lower()
    if name.endswith((".txt", ".md")):
        return _normalise(bytes(file_bytes).decode("utf-8", errors="replace"))
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(file_bytes), strict=True)
            if reader.is_encrypted:
                try:
                    result = reader.decrypt("")
                except Exception:
                    result = 0
                if not result:
                    raise ExtractionError("This PDF is encrypted or password protected.")
            if len(reader.pages) > MAX_PDF_PAGES:
                raise ExtractionError(f"PDF has more than the {MAX_PDF_PAGES}-page limit.")
            pages, total = [], 0
            for page in reader.pages:
                page_text = page.extract_text() or ""
                total += len(page_text)
                if total > MAX_EXTRACTED_CHARS:
                    raise ExtractionError(f"Extracted text exceeds the {MAX_EXTRACTED_CHARS:,}-character limit.")
                pages.append(page_text)
        except ExtractionError:
            raise
        except Exception:
            raise ExtractionError("Could not read this PDF. Check that it is a valid, unencrypted PDF.") from None
        text = _normalise("\n\n".join(pages))
        if len(text) < 20:
            raise ExtractionError("No selectable text found. Scanned/handwritten PDFs need OCR, or paste the answer manually.")
        return text
    raise ExtractionError("Unsupported file type. Upload a PDF or plain-text file.")
