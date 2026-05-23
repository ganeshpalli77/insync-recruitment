"""Resume file parsing: PDF/DOCX via LlamaParse, TXT native, with per-file cache."""

from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from src.core.parsers.llamaparse import parse_pdf_or_docx
from src.core.parsers.text import parse_text
from src.services.cache import (
    get_cached_parsed_file,
    hash_bytes,
    set_cached_parsed_file,
)


@dataclass(slots=True)
class ParsedFile:
    filename: str
    text: str
    file_hash: str
    from_cache: bool


def _extension(filename: str) -> str:
    return "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


async def parse_resume_bytes(filename: str, content: bytes) -> ParsedFile:
    """Dispatch to the right parser by file extension. Cached by file-hash."""
    file_hash = hash_bytes(content)
    cached = await get_cached_parsed_file(file_hash)
    if cached is not None:
        logger.info("parse_cache_hit | filename={} hash={}", filename, file_hash[:8])
        return ParsedFile(filename=filename, text=cached, file_hash=file_hash, from_cache=True)

    ext = _extension(filename)
    if ext == ".txt":
        text = parse_text(content)
    elif ext in (".pdf", ".docx"):
        text = await parse_pdf_or_docx(filename, content)
    else:
        raise ValueError(f"Unsupported file extension: {ext or '(none)'}")

    await set_cached_parsed_file(file_hash, text)
    return ParsedFile(filename=filename, text=text, file_hash=file_hash, from_cache=False)
