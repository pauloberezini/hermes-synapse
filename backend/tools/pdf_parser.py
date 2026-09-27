"""
backend/tools/pdf_parser.py — Multi-format PDF RAG Pipeline

Provides local PDF parsing without external SaaS dependencies.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger("hermes.pdf_parser")

def parse_pdf(file_path: str) -> Optional[str]:
    """
    Parses a local PDF file and extracts its text content for RAG indexing.
    Requires `pypdf` (install via `pip install pypdf`).
    """
    if not os.path.exists(file_path):
        logger.error(f"[PDFParser] File not found: {file_path}")
        return None

    try:
        import pypdf
    except ImportError:
        logger.error("[PDFParser] The 'pypdf' library is missing. Please run: pip install pypdf")
        return None

    try:
        text_content = []
        with open(file_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            for page_num, page in enumerate(reader.pages):
                page_text = page.extract_text()
                if page_text:
                    text_content.append(page_text)
        
        full_text = "\n\n".join(text_content)
        logger.info(f"[PDFParser] Extracted {len(full_text)} characters from {file_path}")
        return full_text
    except Exception as e:
        logger.error(f"[PDFParser] Failed to parse PDF {file_path}: {e}")
        return None

def index_pdf_to_memory(file_path: str, doc_id: str = "") -> bool:
    """
    End-to-end pipeline: Parse PDF -> MemoryGuard -> Qdrant/Postgres
    """
    text = parse_pdf(file_path)
    if not text:
        return False
        
    title = os.path.basename(file_path)
    if not doc_id:
        doc_id = title.replace(" ", "_").lower()

    from backend.memory import QdrantMemoryEngine
    engine = QdrantMemoryEngine()
    
    # QdrantMemoryEngine.index_document automatically applies MemoryGuard internally
    return engine.index_document(doc_id=doc_id, title=title, text=text, source="upload", note_path=file_path)
