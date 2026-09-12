"""Consistent, safe formatting helpers for user-facing Telegram messages."""

from __future__ import annotations

import html
from collections.abc import Sequence


def safe_telegram_html(
    value: object,
    fallback: str = "—",
    *,
    limit: int = 500,
) -> str:
    """Normalize, shorten, and HTML-escape a value for Telegram HTML mode."""
    normalized = " ".join(str(value or fallback).split()) or fallback
    if len(normalized) > limit:
        normalized = f"{normalized[: limit - 1].rstrip()}…"
    return html.escape(normalized, quote=True)


def telegram_status_card(
    icon: str,
    title: str,
    *,
    message: str | None = None,
    fields: Sequence[tuple[str, str, object]] = (),
    action_title: str | None = None,
    action: str | None = None,
    steps: Sequence[str] = (),
    note: str | None = None,
) -> str:
    """Build a compact status card from plain-text, automatically escaped values."""
    sections = [
        f"{safe_telegram_html(icon, '', limit=8)} "
        f"<b>{safe_telegram_html(title, 'Update', limit=80)}</b>"
    ]

    if message:
        sections.append(safe_telegram_html(message, limit=1000))

    if fields:
        field_lines = []
        for field_icon, label, value in fields:
            field_lines.append(
                f"{safe_telegram_html(field_icon, '', limit=8)} "
                f"<b>{safe_telegram_html(label, 'Details', limit=60)}:</b> "
                f"{safe_telegram_html(value, limit=300)}"
            )
        sections.append("\n".join(field_lines))

    action_lines = []
    if action:
        action_lines.append(safe_telegram_html(action, limit=1000))
    action_lines.extend(
        f"{index}. {safe_telegram_html(step, limit=500)}"
        for index, step in enumerate(steps, 1)
    )
    if action_lines:
        action_heading = action_title or "What to do next"
        sections.append(
            f"✅ <b>{safe_telegram_html(action_heading, limit=80)}</b>\n"
            + "\n".join(action_lines)
        )

    if note:
        sections.append(
            f"ℹ️ <i>{safe_telegram_html(note, limit=800)}</i>"
        )

    return "\n\n".join(sections)
