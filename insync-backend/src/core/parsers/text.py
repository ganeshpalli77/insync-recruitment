"""Native UTF-8 parser for .txt resumes."""

from __future__ import annotations


def parse_text(content: bytes) -> str:
    # Try UTF-8 first, fall back to latin-1 (never raises) for legacy resumes.
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("latin-1", errors="replace")
