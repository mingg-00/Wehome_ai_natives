"""로컬 대시보드 서버.

`python main.py serve` → http://127.0.0.1:8765 에서 대시보드를 띄우고,
"🚀 지금 게시" 버튼 클릭 → /api/social/publish 로 단건 즉시 게시(토큰 없으면 dry-run).
정적 파일(file://)로는 버튼이 동작하지 않으므로 이 서버로 열어야 한다. localhost 전용.
"""
from __future__ import annotations

import json
import os
import secrets
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from . import dashboard, social

# .env에 DASHBOARD_TOKEN이 있으면 사용, 없으면 서버 시작마다 새 토큰 생성
_SESSION_TOKEN: str = os.getenv("DASHBOARD_TOKEN") or secrets.token_hex(16)


class _Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body, ctype="text/html; charset=utf-8"):
        b = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _is_local_origin(self) -> bool:
        origin = self.headers.get("Origin", "")
        referer = self.headers.get("Referer", "")
        allowed = ("http://127.0.0.1:8765", "http://localhost:8765")
        src = origin or referer
        return not src or any(src.startswith(a) for a in allowed)

    def _is_authed(self) -> bool:
        """URL 쿼리 파라미터 _t 로 세션 토큰 검증."""
        u = urllib.parse.urlparse(self.path)
        token = urllib.parse.parse_qs(u.query).get("_t", [""])[0]
        return secrets.compare_digest(token, _SESSION_TOKEN)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        if u.path in ("/", "/index.html"):
            self._send(200, dashboard.build())  # 매 요청 최신 상태로 렌더
        elif u.path == "/api/social/publish":
            if not (self._is_local_origin() and self._is_authed()):
                self._send(403, json.dumps({"error": "인증 실패 — 올바른 URL로 접근하세요"}),
                           "application/json")
                return
            pid = urllib.parse.parse_qs(u.query).get("id", [""])[0]
            res = social.publish_one(pid)
            self._send(200, json.dumps(res, ensure_ascii=False), "application/json; charset=utf-8")
        elif u.path == "/api/social/generate":
            if not (self._is_local_origin() and self._is_authed()):
                self._send(403, json.dumps({"error": "인증 실패 — 올바른 URL로 접근하세요"}),
                           "application/json")
                return
            qs = urllib.parse.parse_qs(u.query)
            topic = qs.get("topic", [""])[0].strip()
            platform = qs.get("platform", [""])[0].strip()
            if not topic:
                self._send(200, json.dumps({"error": "주제를 입력하세요"}),
                           "application/json; charset=utf-8")
                return
            platforms = None if (not platform or platform == "all") else [platform]
            created = social.generate_and_queue(topic, platforms)
            self._send(200, json.dumps({"created": created}, ensure_ascii=False),
                       "application/json; charset=utf-8")
        else:
            self._send(404, "not found")

    def log_message(self, *a):  # 조용히
        pass


def serve(port: int = 8765, open_browser: bool = True) -> None:
    httpd = HTTPServer(("127.0.0.1", port), _Handler)
    url = f"http://127.0.0.1:{port}/?_t={_SESSION_TOKEN}"
    print(f"🌐 대시보드 서버 실행: {url}")
    print(f"   세션 토큰: {_SESSION_TOKEN}")
    print('   SNS 큐에서 "🚀 지금 게시" 클릭 → 즉시 게시(토큰 없으면 dry-run)')
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n서버 종료.")
        httpd.server_close()
