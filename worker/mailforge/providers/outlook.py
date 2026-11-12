"""Outlook / Microsoft 365 provider via Microsoft Graph (MSAL refresh token, Mail.Read)."""
from __future__ import annotations

from datetime import datetime

import requests

from ..config import env
from .base import EmailMessage, EmailProvider

GRAPH = "https://graph.microsoft.com/v1.0"


def graph_access_token(tenant: str, client_id: str, refresh_token: str, scope: str,
                       client_secret: str | None = None) -> str:
    import msal

    authority = f"https://login.microsoftonline.com/{tenant}"
    app = (
        msal.ConfidentialClientApplication(client_id, client_credential=client_secret, authority=authority)
        if client_secret else msal.PublicClientApplication(client_id, authority=authority)
    )
    res = app.acquire_token_by_refresh_token(refresh_token, scopes=[scope])
    if "access_token" not in res:
        raise RuntimeError(f"Microsoft token refresh failed: {str(res.get('error_description', res))[:200]}")
    return res["access_token"]


class OutlookProvider(EmailProvider):
    def fetch_unread(self, since: datetime, limit: int) -> list[EmailMessage]:
        a = self.account
        token = graph_access_token(
            a.tenant, env(a.client_id_env), env(a.refresh_token_env), "Mail.Read",
            env(a.client_secret_env, required=False) or None,
        )
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {token}",
                          "Prefer": 'outlook.body-content-type="text"'})
        url = f"{GRAPH}/me/mailFolders/inbox/messages"
        params = {
            "$filter": f"isRead eq false and receivedDateTime ge {since.strftime('%Y-%m-%dT%H:%M:%SZ')}",
            "$orderby": "receivedDateTime desc",
            "$top": min(limit, 50),
            "$select": "id,conversationId,subject,from,receivedDateTime,body,internetMessageHeaders",
        }
        out: list[EmailMessage] = []
        while url and len(out) < limit:
            r = s.get(url, params=params, timeout=30)
            r.raise_for_status()
            j = r.json()
            out += [self._parse(m) for m in j.get("value", [])]
            url, params = j.get("@odata.nextLink"), None
        return out[:limit]

    def _parse(self, m: dict) -> EmailMessage:
        h = {x["name"].lower(): x["value"] for x in m.get("internetMessageHeaders") or []}
        fr = m.get("from", {}).get("emailAddress", {})
        body = m.get("body", {})
        is_html = body.get("contentType", "text").lower() == "html"
        return EmailMessage(
            account_id=self.account.id, message_id=m["id"], thread_id=m.get("conversationId", m["id"]),
            sender=f"{fr.get('name', '')} <{fr.get('address', '')}>", subject=m.get("subject") or "(no subject)",
            date=datetime.fromisoformat(m["receivedDateTime"].replace("Z", "+00:00")),
            text="" if is_html else body.get("content", ""),
            html=body.get("content", "") if is_html else "", headers=h,
        )
