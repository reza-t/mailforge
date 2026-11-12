"""Yahoo Mail provider: IMAP over SSL with an App Password."""
from __future__ import annotations

import email
import imaplib
from datetime import UTC, datetime
from email import policy
from email.utils import parsedate_to_datetime

from ..config import env
from .base import EmailMessage, EmailProvider

HOST, PORT = "imap.mail.yahoo.com", 993


class YahooProvider(EmailProvider):
    def fetch_unread(self, since: datetime, limit: int) -> list[EmailMessage]:
        a = self.account
        imap = imaplib.IMAP4_SSL(HOST, PORT, timeout=30)
        try:
            imap.login(env(a.username_env), env(a.password_env))
            imap.select("INBOX", readonly=True)  # readonly: never flips \Seen
            # IMAP SINCE is date-granular; precise cut-off applied below.
            _, data = imap.search(None, "UNSEEN", "SINCE", since.strftime("%d-%b-%Y"))
            uids = data[0].split()[-limit:][::-1]
            out = []
            for uid in uids:
                _, parts = imap.fetch(uid, "(BODY.PEEK[])")
                raw = next((p[1] for p in parts if isinstance(p, tuple)), None)
                if raw:
                    msg = self._parse(uid.decode(), raw)
                    if msg.date >= since:
                        out.append(msg)
            return out
        finally:
            try:
                imap.logout()
            except Exception:
                pass

    def _parse(self, uid: str, raw: bytes) -> EmailMessage:
        m = email.message_from_bytes(raw, policy=policy.default)
        txt, html = m.get_body(("plain",)), m.get_body(("html",))
        try:
            date = parsedate_to_datetime(m["Date"])
            if date.tzinfo is None:
                date = date.replace(tzinfo=UTC)
        except Exception:
            date = datetime.now(UTC)
        mid = (m["Message-ID"] or uid).strip()
        return EmailMessage(
            account_id=self.account.id, message_id=mid,
            thread_id=(m["References"] or m["In-Reply-To"] or mid).split()[0],
            sender=str(m["From"] or ""), subject=str(m["Subject"] or "(no subject)"), date=date,
            text=txt.get_content() if txt else "", html=html.get_content() if html else "",
            headers={k.lower(): str(v) for k, v in m.items()},
        )
