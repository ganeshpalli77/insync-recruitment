"""Tiny input sanitizer for user-supplied text fields.

Goals: drop NUL bytes (Postgres rejects them anyway), strip raw HTML/script
tags (don't render unsanitized text in the email PDF), and trim whitespace.
We do NOT do generic XSS escaping — that is the responsibility of every
HTML-rendering surface (jinja autoescape, etc.).
"""

from __future__ import annotations

import re

_TAG = re.compile(r"<[^>]+>")
_NUL = "\x00"


def clean_text(value: str, *, max_length: int | None = None) -> str:
    """Strip NUL bytes + raw tags + collapse trailing whitespace."""
    if not value:
        return ""
    cleaned = value.replace(_NUL, "")
    cleaned = _TAG.sub("", cleaned).strip()
    if max_length is not None and len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    return cleaned
