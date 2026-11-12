"""Gmail API provider (OAuth2 refresh token, gmail.readonly)."""
from __future__ import annotations

import base64
from datetime import UTC, datetime

import requests

from ..config import env
from .base import EmailMessage, EmailProvider

API = "https://gmail.googleapis.com/gmail/v1/users/me"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def gmail_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    r = requests.post(
        TOKEN_URL,
        data={"client_id": client_id, "client_secret": client_secret,
              "refresh_token": refresh_token, "grant_type": "refresh_token"},
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Google token refresh failed: {r.json().get('error_description', r.status_code)}")
    return r.json()["access_token"]


def _b64(data: str) -> str:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")


def _walk(part: dict, out: dict[str, str]) -> None:
    mt = part.get("mimeType", "")
    data = part.get("body", {}).get("data")
    if data and mt in ("text/plain", "text/html") and not part.get("filename"):
        out[mt] += _b64(data)
    for p in part.get("parts", []):
        _walk(p, out)


class GmailProvider(EmailProvider):
    def fetch_unread(self, since: datetime, limit: int) -> list[EmailMessage]:
        a = self.account
        token = gmail_access_token(env(a.client_id_env), env(a.client_secret_env), env(a.refresh_token_env))
        s = requests.Session()
        s.headers["Authorization"] = f"Bearer {token}"
        r = s.get(f"{API}/messages", timeout=30, params={
            "q": f"is:unread in:inbox after:{int(since.timestamp())}",
            "maxResults": min(limit, 100)})
        r.raise_for_status()
        out = []
        for ref in r.json().get("messages", []):
            m = s.get(f"{API}/messages/{ref['id']}", params={"format": "full"}, timeout=30)
            m.raise_for_status()
            out.append(self._parse(m.json()))
        return out

    def _parse(self, j: dict) -> EmailMessage:
        payload = j.get("payload", {})
        h = {x["name"].lower(): x["value"] for x in payload.get("headers", [])}
        bodies = {"text/plain": "", "text/html": ""}
        _walk(payload, bodies)
        return EmailMessage(
            account_id=self.account.id, message_id=j["id"], thread_id=j.get("threadId", j["id"]),
            sender=h.get("from", ""), subject=h.get("subject", "(no subject)"),
            date=datetime.fromtimestamp(int(j["internalDate"]) / 1000, tz=UTC),
            text=bodies["text/plain"], html=bodies["text/html"], headers=h,
        )
