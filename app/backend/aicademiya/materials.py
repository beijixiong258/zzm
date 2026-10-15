"""Synchronous native + local CPU OCR previews; retain originals privately."""
from .material_extraction import SUPPORTED, extract_document

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def extract(path):
    """Legacy three-value API; new callers should persist extraction_report."""
    result = extract_document(path)
    return result["status"], result["excerpt"], result["warning"]
