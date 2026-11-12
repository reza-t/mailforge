#!/usr/bin/env python3
"""Obtain OAuth2 refresh tokens for MailForge (run on your own machine, not in Docker).

  pip install google-auth-oauthlib msal
  python scripts/get_oauth_token.py google    [--send]
  python scripts/get_oauth_token.py microsoft [--send] [--tenant common]

--send additionally requests send permission (needed only for delivery.method gmail/graph).
Prints the refresh token; paste it into .env. Never commit it.
"""
import argparse
import getpass
import sys


def google(a):
    from google_auth_oauthlib.flow import InstalledAppFlow

    cid = input("Google OAuth client ID: ").strip()
    secret = getpass.getpass("Google OAuth client secret: ").strip()
    scopes = ["https://www.googleapis.com/auth/gmail.readonly"]
    if a.send:
        scopes.append("https://www.googleapis.com/auth/gmail.send")
    cfg = {"installed": {
        "client_id": cid, "client_secret": secret,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": ["http://localhost"]}}
    creds = InstalledAppFlow.from_client_config(cfg, scopes).run_local_server(
        port=0, access_type="offline", prompt="consent")
    return creds.refresh_token


def microsoft(a):
    import msal

    cid = input("Azure app (client) ID: ").strip()
    app = msal.PublicClientApplication(cid, authority=f"https://login.microsoftonline.com/{a.tenant}")
    scopes = ["Mail.Read"] + (["Mail.Send"] if a.send else [])  # MSAL adds offline_access itself
    flow = app.initiate_device_flow(scopes=scopes)
    if "user_code" not in flow:
        sys.exit(f"Device flow failed: {flow}")
    print(flow["message"])
    res = app.acquire_token_by_device_flow(flow)
    if "refresh_token" not in res:
        sys.exit(f"No refresh token: {res.get('error_description', res)}")
    return res["refresh_token"]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("provider", choices=["google", "microsoft"])
    p.add_argument("--send", action="store_true")
    p.add_argument("--tenant", default="common")
    a = p.parse_args()
    token = google(a) if a.provider == "google" else microsoft(a)
    print("\nRefresh token (store in .env):\n" + token)


if __name__ == "__main__":
    main()
