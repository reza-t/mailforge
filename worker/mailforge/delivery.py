"""Deliver the Markdown report as HTML + plain-text email (SMTP, Gmail API or MS Graph)."""
from __future__ import annotations

import base64
import smtplib
import ssl
from email.message import EmailMessage as MimeMessage

import markdown
import requests

from .config import Delivery, env
from .providers.gmail import API as GMAIL_API
from .providers.gmail import gmail_access_token
from .providers.outlook import GRAPH, graph_access_token

LOOP_HEADER = ("X-MailForge-Report", "true")


def subject_for(date: str) -> str:
    return f"[MailForge] Daily Briefing — {date}"


def render_html(md_text: str) -> str:
    # Report text is LLM output derived from untrusted mail: neutralise raw HTML tags.
    body = markdown.markdown(md_text.replace("<", "&lt;"), extensions=["tables", "sane_lists"])
    return (
        '<html><body style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
        f'max-width:720px;margin:auto;line-height:1.5">{body}</body></html>'
    )


def build_message(md_text: str, date: str, sender: str, recipient: str) -> MimeMessage:
    m = MimeMessage()
    m["Subject"], m["From"], m["To"] = subject_for(date), sender, recipient
    m[LOOP_HEADER[0]] = LOOP_HEADER[1]
    m.set_content(md_text)
    m.add_alternative(render_html(md_text), subtype="html")
    return m


def send(md_text: str, date: str, d: Delivery) -> None:
    sender, recipient = env(d.sender_env), env(d.recipient_env)
    if d.method == "smtp":
        m = build_message(md_text, date, sender, recipient)
        user, pw = env(d.smtp_user_env, required=False) or sender, env(d.smtp_password_env)
        if d.smtp_port == 465:
            with smtplib.SMTP_SSL(d.smtp_host, 465, context=ssl.create_default_context(), timeout=30) as s:
                s.login(user, pw)
                s.send_message(m)
        else:
            with smtplib.SMTP(d.smtp_host, d.smtp_port, timeout=30) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(user, pw)
                s.send_message(m)
    elif d.method == "gmail":
        m = build_message(md_text, date, sender, recipient)
        tok = gmail_access_token(env(d.oauth_client_id_env), env(d.oauth_client_secret_env),
                                 env(d.oauth_refresh_token_env))
        raw = base64.urlsafe_b64encode(m.as_bytes()).decode()
        r = requests.post(f"{GMAIL_API}/messages/send", json={"raw": raw},
                          headers={"Authorization": f"Bearer {tok}"}, timeout=30)
        r.raise_for_status()
    else:  # graph
        tok = graph_access_token(d.oauth_tenant, env(d.oauth_client_id_env), env(d.oauth_refresh_token_env),
                                 "Mail.Send", env(d.oauth_client_secret_env, required=False) or None)
        payload = {"message": {
            "subject": subject_for(date),
            "body": {"contentType": "HTML", "content": render_html(md_text)},
            "toRecipients": [{"emailAddress": {"address": recipient}}],
            "internetMessageHeaders": [{"name": LOOP_HEADER[0], "value": LOOP_HEADER[1]}],
        }}
        r = requests.post(f"{GRAPH}/me/sendMail", json=payload,
                          headers={"Authorization": f"Bearer {tok}"}, timeout=30)
        r.raise_for_status()
