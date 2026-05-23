"""Magic-bytes verification: confirms the file's content matches its claimed
extension. Cheap defense against renamed executables / mismatched types.
"""

from __future__ import annotations

# (extension, set of magic-byte prefixes that may legitimately start that
# file type). DOCX/ZIP and PDF prefixes are stable and well-documented.
_MAGIC: dict[str, tuple[bytes, ...]] = {
    ".pdf": (b"%PDF",),
    # DOCX is a ZIP under the hood; both PK\x03\x04 (most common) and the
    # empty-archive PK\x05\x06 are valid first-blocks.
    ".docx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    # .txt is intentionally permissive — anything decodable to UTF-8 or
    # latin-1 is fine; magic-bytes have no meaning for plain text.
    ".txt": (),
}


def matches_extension(filename: str, content: bytes) -> bool:
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    prefixes = _MAGIC.get(ext)
    if prefixes is None:
        return False  # unknown extension — caller should reject upstream
    if not prefixes:
        return True  # txt: no signature check
    head = content[:16]
    return any(head.startswith(p) for p in prefixes)
