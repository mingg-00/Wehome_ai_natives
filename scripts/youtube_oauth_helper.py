from __future__ import annotations

import json
import os
from pathlib import Path
import threading
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen


REDIRECT_URI = "http://localhost:8080/"
AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
DEFAULT_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
OUTPUT_PATH = Path(__file__).resolve().parent.parent / "output" / "youtube_oauth_tokens.json"


@dataclass
class OAuthResult:
    code: str = ""
    error: str = ""
    state: str = ""


result = OAuthResult()
result_ready = threading.Event()


def _build_auth_url(client_id: str, scopes: list[str]) -> str:
    scope_value = " ".join(scopes)
    return (
        f"{AUTH_ENDPOINT}"
        f"?client_id={quote(client_id, safe='')}"
        f"&redirect_uri={quote(REDIRECT_URI, safe='')}"
        f"&response_type=code"
        f"&scope={quote(scope_value, safe='')}"
        f"&access_type=offline"
        f"&prompt=consent"
        f"&include_granted_scopes=true"
    )


def _exchange_code_for_tokens(client_id: str, client_secret: str, code: str) -> dict:
    payload = (
        f"code={quote(code, safe='')}"
        f"&client_id={quote(client_id, safe='')}"
        f"&client_secret={quote(client_secret, safe='')}"
        f"&redirect_uri={quote(REDIRECT_URI, safe='')}"
        f"&grant_type=authorization_code"
    ).encode("utf-8")

    request = Request(
        TOKEN_ENDPOINT,
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )

    with urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8")

    return json.loads(raw)


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "error" in params:
            result.error = params["error"][0]
            result_ready.set()
            self._write_response(400, "OAuth authorization failed. You can close this tab.")
            return

        code = params.get("code", [""])[0]
        state = params.get("state", [""])[0]
        if not code:
            self._write_response(400, "Missing authorization code.")
            return

        result.code = code
        result.state = state
        result_ready.set()
        self._write_response(200, "Authorization received. You can close this tab.")

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _write_response(self, status: int, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def main() -> int:
    client_id = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "").strip()
    scopes_env = os.getenv("YOUTUBE_SCOPES", "").strip()
    scopes = [scope for scope in scopes_env.split() if scope] if scopes_env else DEFAULT_SCOPES

    if not client_id:
        print("GOOGLE_CLIENT_ID is required.")
        return 1
    if not client_secret:
        print("GOOGLE_CLIENT_SECRET is required.")
        return 1

    auth_url = _build_auth_url(client_id, scopes)
    server = HTTPServer(("localhost", 8080), OAuthCallbackHandler)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    print("Open this URL in your browser:")
    print(auth_url)
    print()
    print("Waiting for Google redirect on http://localhost:8080/ ...")

    try:
        webbrowser.open(auth_url, new=1)
    except Exception:
        pass

    try:
        result_ready.wait()
    finally:
        server.shutdown()
        server.server_close()

    if result.error:
        print(f"OAuth error: {result.error}")
        return 1

    if not result.code:
        print("No authorization code received.")
        return 1

    print("Authorization code received.")
    print("Exchanging code for tokens...")

    try:
        token_data = _exchange_code_for_tokens(client_id, client_secret, result.code)
    except Exception as exc:
        print(f"Token exchange failed: {exc}")
        return 1

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(token_data, ensure_ascii=False, indent=2), encoding="utf-8")

    refresh_token = token_data.get("refresh_token", "")
    access_token = token_data.get("access_token", "")
    expires_in = token_data.get("expires_in", "")

    print()
    print("Token response:")
    print(json.dumps(token_data, ensure_ascii=False, indent=2))
    print(f"Saved token response to: {OUTPUT_PATH}")
    print()
    print("Use these values in .env:")
    if access_token:
        print(f"YOUTUBE_ACCESS_TOKEN={access_token}")
    if refresh_token:
        print(f"GOOGLE_REFRESH_TOKEN={refresh_token}")
    print(f"GOOGLE_CLIENT_ID={client_id}")
    print(f"GOOGLE_CLIENT_SECRET={client_secret}")
    if expires_in:
        print(f"Access token expires in: {expires_in} seconds")
    if not refresh_token:
        print("No refresh_token returned. Re-run with prompt=consent and ensure offline access is allowed.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
