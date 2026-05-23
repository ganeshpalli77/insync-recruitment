"""LlamaParse wrapper: premium-mode text extraction for PDF + DOCX."""

from __future__ import annotations

import tempfile
from pathlib import Path

from loguru import logger

from src.config import get_settings


async def parse_pdf_or_docx(filename: str, content: bytes) -> str:
    """Extract plain text from a PDF/DOCX resume via LlamaParse premium mode.

    LlamaParse only accepts file paths, so we write to a NamedTemporaryFile.
    """
    settings = get_settings()
    if not settings.llama_cloud_api_key:
        raise RuntimeError(
            "LLAMA_CLOUD_API_KEY is not set — resume parsing requires LlamaParse."
        )

    # Import lazily so unit tests don't pay LlamaIndex's import cost.
    from llama_parse import LlamaParse

    parser = LlamaParse(
        api_key=settings.llama_cloud_api_key,
        result_type=settings.llamaparse_result_type,  # "text"
        verbose=False,
        language="en",
        premium_mode=(settings.llamaparse_mode == "premium"),
    )

    suffix = Path(filename).suffix or ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        docs = await parser.aload_data(str(tmp_path))
    finally:
        tmp_path.unlink(missing_ok=True)

    text = "\n\n".join(d.text for d in docs if getattr(d, "text", None))
    if not text.strip():
        logger.warning("llamaparse_empty_text | filename={}", filename)
    return text
