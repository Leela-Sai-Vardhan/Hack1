import os
import logging
from pathlib import Path
from schemas import CreditCase

logger = logging.getLogger(__name__)


def extract_text_from_pdf(file_path: str) -> str:
    """Extract text using pdfplumber (native PDFs) with OCR fallback."""
    text = ""
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages[:25]:
                page_text = page.extract_text() or ""
                text += page_text + "\n"
        if len(text.strip()) < 100:
            logger.info(f"Low native text in {file_path}, trying OCR...")
            text = _ocr_pdf(file_path)
    except Exception as e:
        logger.warning(f"pdfplumber failed for {file_path}: {e}")
        text = _ocr_pdf(file_path)
    return text[:50000]


def _ocr_pdf(file_path: str) -> str:
    """Tesseract OCR fallback for scanned PDFs."""
    try:
        import pytesseract
        import pdfplumber
        text = ""
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages[:10]:
                img = page.to_image(resolution=200).original
                page_text = pytesseract.image_to_string(img, lang="eng")
                text += page_text + "\n"
        return text
    except Exception as e:
        logger.error(f"OCR failed for {file_path}: {e}")
        return f"[Text extraction failed: {e}]"


def classify_document(filename: str, declared_type: str = "unknown") -> str:
    """Classify document by declared type or filename heuristics."""
    if declared_type and declared_type != "unknown":
        return declared_type
    fname = Path(filename).name.lower()
    rules = {
        "gstr": "gst_filing", "gst": "gst_filing",
        "bank": "bank_statement", "statement": "bank_statement",
        "itr": "itr", "income_tax": "itr",
        "annual": "annual_report", "ar_": "annual_report",
        "board": "board_minutes", "minutes": "board_minutes",
        "sanction": "sanction_letter",
        "rating": "rating_report", "crisil": "rating_report",
        "icra": "rating_report", "care": "rating_report",
        "legal": "legal_notice", "notice": "legal_notice",
        "mca": "mca_filing", "roc": "mca_filing",
        "shareholding": "shareholding_pattern",
    }
    for keyword, doc_type in rules.items():
        if keyword in fname:
            return doc_type
    return "unknown"


def get_extracted_text(file_path: str) -> str:
    """Return cached extracted text, or extract on the fly."""
    txt_path = file_path + ".extracted.txt"
    if os.path.exists(txt_path):
        with open(txt_path, "r", encoding="utf-8") as f:
            return f.read()
    return extract_text_from_pdf(file_path)


async def ingest_documents(case: CreditCase) -> CreditCase:
    """Extract text from all uploaded documents and cache to .txt sidecars."""
    for doc_type, file_path in case.raw_documents.items():
        if not os.path.exists(file_path):
            case.errors.append({"stage": "ingestor", "doc_type": doc_type,
                                 "error": f"File not found: {file_path}"})
            continue
        try:
            text = extract_text_from_pdf(file_path)
            txt_path = file_path + ".extracted.txt"
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(text)
            logger.info(f"Ingested {doc_type}: {len(text)} chars")
        except Exception as e:
            case.errors.append({"stage": "ingestor", "doc_type": doc_type,
                                 "error": str(e)})
    return case
