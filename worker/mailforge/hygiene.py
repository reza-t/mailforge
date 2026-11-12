"""Deterministic, zero-token pre-filtering and payload hygiene."""
from __future__ import annotations

import fnmatch
import re

from bs4 import BeautifulSoup

from .config import Settings
from .providers.base import EmailMessage

MAX_BODY_CHARS = 3500
TRUNC_MARK = "[TRUNCATED]"
REPORT_SUBJECT_PREFIX = "[MailForge] Daily Briefing"

# First marker found cuts everything after it (quoted history).
_QUOTE_MARKERS = [
    re.compile(r"^-{2,}\s*Original Message\s*-{2,}", re.I | re.M),
    re.compile(r"^On\b[^\n]{0,200}\n?[^\n]{0,120}\bwrote:\s*$", re.I | re.M),
    re.compile(r"^Am\b[^\n]{0,200}\bschrieb\b[^\n]{0,120}:\s*$", re.I | re.M),
    re.compile(r"^_{5,}\s*\n\s*From:", re.I | re.M),  # Outlook separator
]


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["style", "script", "head", "title", "img"]):
        tag.decompose()  # img removal also kills tracking pixels
    return soup.get_text("\n")


def strip_quotes(text: str) -> str:
    cut = len(text)
    for rx in _QUOTE_MARKERS:
        m = rx.search(text)
        if m:
            cut = min(cut, m.start())
    lines = [ln for ln in text[:cut].splitlines() if not ln.lstrip().startswith(">")]
    return "\n".join(lines)


def truncate(text: str, limit: int = MAX_BODY_CHARS) -> str:
    return text if len(text) <= limit else text[:limit] + "\n" + TRUNC_MARK


def clean_body(msg: EmailMessage) -> str:
    raw = msg.text.strip() or (html_to_text(msg.html) if msg.html else "")
    text = strip_quotes(raw)
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return truncate(text)


def is_own_report(msg: EmailMessage) -> bool:
    return (
        msg.headers.get("x-mailforge-report", "").strip().lower() == "true"
        or msg.subject.strip().startswith(REPORT_SUBJECT_PREFIX)
    )


def _domain(address: str) -> str:
    return address.rpartition("@")[2].lower()


def is_vip(msg: EmailMessage, vip_domains: list[str]) -> bool:
    d = _domain(msg.address)
    return any(d == v.lower() or d.endswith("." + v.lower()) for v in vip_domains)


def filter_reason(msg: EmailMessage, s: Settings) -> str | None:
    """Return why a message is discarded, or None to keep it."""
    if is_own_report(msg):
        return "own-report"
    addr = msg.address
    if any(fnmatch.fnmatch(addr, p.lower()) for p in s.ignore_senders):
        return "ignored-sender"
    if is_vip(msg, s.vip_domains):
        return None
    h = msg.headers
    if "list-unsubscribe" in h:
        return "list-unsubscribe"
    if h.get("precedence", "").strip().lower() in {"bulk", "list", "junk"}:
        return "precedence-bulk"
    if h.get("auto-submitted", "no").strip().lower() != "no":
        return "auto-submitted"
    return None
