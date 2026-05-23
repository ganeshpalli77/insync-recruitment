"""Resend HTML email sender with an optional WeasyPrint PDF attachment.

Spec said "Resend's React Email" but that's a Node-only library; this is the
Python-idiomatic equivalent (jinja2 → HTML for the body, same HTML through
WeasyPrint → PDF for the attachment, single source of truth).

WeasyPrint imports GTK at module-load time. On Windows without GTK the
import raises, so we defer + try/except: email still ships, just without
the PDF attachment.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

import resend
from jinja2 import Environment, FileSystemLoader, select_autoescape
from loguru import logger

from src.config import get_settings
from src.schemas.common import JobSummary
from src.schemas.score import CandidateScore, ScoringMetadata

_TEMPLATE_DIR = Path(__file__).resolve().parent / "email_templates"

# Score-band → (background, foreground) used by the HTML template's badge.
_BAND_BG = {"strong": "#d1fae5", "moderate": "#fef3c7", "weak": "#fee2e2"}
_BAND_FG = {"strong": "#065f46", "moderate": "#92400e", "weak": "#991b1b"}

_jinja: Environment | None = None


def _env() -> Environment:
    global _jinja
    if _jinja is None:
        _jinja = Environment(
            loader=FileSystemLoader(_TEMPLATE_DIR),
            autoescape=select_autoescape(["html", "jinja"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
    return _jinja


def _render(
    template_name: str,
    *,
    job_summary: JobSummary,
    candidates: list[CandidateScore],
    session_id: str,
    metadata: ScoringMetadata | None,
) -> str:
    template = _env().get_template(template_name)
    return template.render(
        job_summary=job_summary.model_dump(),
        candidates=[c.model_dump() for c in candidates],
        session_id=session_id,
        metadata=metadata.model_dump() if metadata else None,
        frontend_url=get_settings().frontend_url,
        band_bg=_BAND_BG,
        band_fg=_BAND_FG,
    )


def render_results_html(
    *,
    job_summary: JobSummary,
    candidates: list[CandidateScore],
    session_id: str,
    metadata: ScoringMetadata | None = None,
) -> str:
    return _render(
        "results.html.jinja",
        job_summary=job_summary,
        candidates=candidates,
        session_id=session_id,
        metadata=metadata,
    )


def render_results_text(
    *,
    job_summary: JobSummary,
    candidates: list[CandidateScore],
    session_id: str,
    metadata: ScoringMetadata | None = None,
) -> str:
    return _render(
        "results.txt.jinja",
        job_summary=job_summary,
        candidates=candidates,
        session_id=session_id,
        metadata=metadata,
    )


def render_results_pdf(html: str) -> bytes | None:
    """HTML → PDF. Returns None if WeasyPrint can't load (e.g., no GTK on Windows)."""
    try:
        from weasyprint import HTML  # type: ignore
    except Exception as e:  # noqa: BLE001
        logger.warning("weasyprint_unavailable | err={}", e)
        return None
    try:
        return HTML(string=html).write_pdf()
    except Exception as e:  # noqa: BLE001
        logger.warning("weasyprint_render_failed | err={}", e)
        return None


async def send_results_email(
    *,
    to: str,
    job_summary: JobSummary,
    candidates: list[CandidateScore],
    session_id: str,
    metadata: ScoringMetadata | None = None,
) -> tuple[bool, str]:
    """Send the templated results email via Resend.

    Returns (success, message_or_id). On any failure returns (False, reason)
    so the route can decide whether to expose the reason to the user.
    """
    settings = get_settings()
    if not settings.resend_api_key:
        logger.info("resend_not_configured | skipping email send for {}", to)
        return False, "Email sending is not configured on this server."

    html = render_results_html(
        job_summary=job_summary,
        candidates=candidates,
        session_id=session_id,
        metadata=metadata,
    )
    text = render_results_text(
        job_summary=job_summary,
        candidates=candidates,
        session_id=session_id,
        metadata=metadata,
    )
    pdf_bytes = render_results_pdf(html)

    resend.api_key = settings.resend_api_key
    params: dict[str, Any] = {
        "from": f"{settings.email_from_name} <{settings.email_from}>",
        "to": [to],
        "subject": f"Your top candidates for {job_summary.title} — Insync",
        "html": html,
        "text": text,  # fallback for clients that don't render HTML
    }
    if pdf_bytes:
        filename = (
            f"insync-scores-{job_summary.title.replace(' ', '-').lower()}.pdf"
        )
        params["attachments"] = [
            {
                "filename": filename,
                "content": base64.b64encode(pdf_bytes).decode("ascii"),
            }
        ]

    try:
        result = resend.Emails.send(params)
    except Exception as e:  # noqa: BLE001
        logger.warning("resend_send_failed | to={} err={}", to, e)
        return False, "We couldn't send the email right now. Please try again later."

    message_id = (
        result.get("id") if isinstance(result, dict) else getattr(result, "id", None)
    )
    return True, str(message_id or "sent")
