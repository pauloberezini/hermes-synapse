#!/usr/bin/env python3
"""
Google Calendar OAuth2 — manual copy-paste flow (most reliable).

Run on your Mac:
    cd /Users/pauloberezini/Documents/private/git/jarvis
    python3 backend/google_auth.py

Steps:
  1. A URL will be printed — open it in your browser (incognito recommended)
  2. Log into Google and click "Allow"
  3. Your browser will try to open localhost and show an error — that's fine
  4. Copy the FULL URL from the browser address bar (starts with http://localhost:...)
  5. Paste it here when prompted
"""

import os
import sys
import json
import threading
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

SCOPES     = ["https://www.googleapis.com/auth/calendar"]
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DATA_DIR   = os.path.join(BASE_DIR, "data")
CREDS_PATH = os.path.join(DATA_DIR, "google_credentials.json")
TOKEN_PATH = os.path.join(DATA_DIR, "google_token.json")
# Google "Desktop app" OAuth clients allow ANY localhost port per RFC 8252
# No need to register http://localhost:9120 in GCP console separately
PORT       = 9120

# ── Global to capture the redirect from browser ──────────────────────────────
_captured = {}

class _CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        _captured["url"] = f"http://localhost:{PORT}{self.path}"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"""
        <html><body style="font-family:sans-serif;padding:40px;background:#111;color:#0f0">
        <h2>&#x2705; Authorization complete!</h2>
        <p>You can close this tab and return to the terminal.</p>
        </body></html>
        """)
    def log_message(self, *a): pass  # silence server logs


def _start_callback_server():
    srv = HTTPServer(("localhost", PORT), _CallbackHandler)
    srv.handle_request()   # handle exactly one request then stop


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    if not os.path.exists(CREDS_PATH):
        print(f"❌  Credentials not found: {CREDS_PATH}")
        return

    try:
        from google_auth_oauthlib.flow import Flow
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError:
        print("Run: pip3 install --break-system-packages google-auth-oauthlib google-api-python-client")
        sys.exit(1)

    # ── If we already have a valid token just refresh it ─────────────────────
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
        if creds and creds.valid:
            print(f"✅  Token already valid: {TOKEN_PATH}")
            _verify(build("calendar", "v3", credentials=creds, cache_discovery=False))
            return
        if creds and creds.expired and creds.refresh_token:
            print("🔄  Refreshing existing token...")
            try:
                creds.refresh(Request())
                with open(TOKEN_PATH, "w") as f:
                    f.write(creds.to_json())
                print(f"✅  Token refreshed: {TOKEN_PATH}")
                _verify(build("calendar", "v3", credentials=creds, cache_discovery=False))
                return
            except Exception as e:
                print(f"⚠️  Failed to refresh token: {e}")
                print("🗑️  Removing invalid token and starting fresh authentication...")
                try:
                    os.remove(TOKEN_PATH)
                except OSError:
                    pass


    # ── Fresh auth ────────────────────────────────────────────────────────────
    redirect_uri = f"http://localhost:{PORT}/"

    flow = Flow.from_client_secrets_file(
        CREDS_PATH,
        scopes=SCOPES,
        redirect_uri=redirect_uri,
    )

    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )

    print("\n" + "="*68)
    print("📋  STEP 1 — Open this URL in your browser (incognito recommended):")
    print("="*68)
    print(f"\n{auth_url}\n")
    print("="*68)
    print("📋  STEP 2 — Log in with Google and click ALLOW")
    print("📋  STEP 3 — Your browser will show an error page — that's expected")
    print("📋  STEP 4 — Copy the ENTIRE URL from the browser address bar")
    print("             (it starts with  http://localhost:9120/?code=...)")
    print("="*68)

    # Start local callback server in background thread
    t = threading.Thread(target=_start_callback_server, daemon=True)
    t.start()

    # Try to open browser automatically (may not work from background task)
    try:
        import webbrowser
        webbrowser.open(auth_url)
        print("\n🌐  Browser opened automatically (if not, open the URL above manually)")
    except Exception:
        pass

    # Wait for callback — either the server catches it OR user pastes the URL
    print("\n⏳  Waiting for browser redirect on http://localhost:9120/ ...")
    t.join(timeout=120)   # wait up to 2 minutes for auto-redirect

    if "url" not in _captured:
        # Auto-redirect didn't work — ask user to paste the URL
        print("\n⚠️   Auto-redirect timed out or was blocked.")
        print("    Paste the full redirect URL from your browser address bar:")
        try:
            pasted = input(">>> ").strip()
        except EOFError:
            pasted = ""
        if pasted:
            _captured["url"] = pasted
        else:
            print("❌  No URL provided. Exiting.")
            return

    redirect_response = _captured["url"]
    print(f"\n✅  Got redirect: {redirect_response[:80]}...")

    # Exchange code for token
    try:
        import os as _os
        _os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"   # allow http://localhost
        flow.fetch_token(authorization_response=redirect_response)
    except Exception as e:
        print(f"❌  Token exchange failed: {e}")
        print("\n💡  Try opening the URL in INCOGNITO mode to avoid cached redirects.")
        return

    creds = flow.credentials
    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())
    print(f"✅  Token saved: {TOKEN_PATH}")

    service = build("calendar", "v3", credentials=creds, cache_discovery=False)
    _verify(service)


def _verify(service):
    try:
        items = service.calendarList().list().execute().get("items", [])
        print(f"\n📅  Connected! {len(items)} calendar(s):")
        for c in items[:5]:
            flag = " ← primary" if c.get("primary") else ""
            print(f"    • {c.get('summary','(unnamed)')}{flag}")
        print("\n🚀  Vexa is authorized to read and write your Google Calendar!\n")
    except Exception as e:
        print(f"⚠️   Connected but list failed: {e}")


if __name__ == "__main__":
    main()
