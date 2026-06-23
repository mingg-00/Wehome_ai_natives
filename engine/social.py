"""SNS 자동 포스팅 에이전트 (자사 브랜드 계정 전용).

범위: 위홈 자사 계정(Instagram·Threads·X·Pinterest·Facebook)에 공식 API로 게시.
⛔ 남의 커뮤니티(레딧 등) 자동 게시·카르마 파밍은 하지 않는다(별도 radar가 사람 게시).

흐름: 생성(LLM) → 검수(governance) → 예약 큐 → 사람 승인 → (예약시간에) 자동 게시.
- 플랫폼 토큰이 .env에 있으면 실제 게시, 없으면 dry-run(미리보기)로 안전하게 동작.
- 이미지가 필요한 IG/Pinterest는 이미지 자산이 없으면 dry-run(주석 표시).
- 영상(mp4)은 X·Facebook에 직접 업로드. Threads는 공개 URL 필요로 텍스트 폴백.
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request

from . import brand, utm
from .config import OUTPUT_DIR, settings
from .llm import chat_json
from . import schedule as _sched
from . import activity_log as _alog

PLATFORMS = ["instagram", "threads", "x", "pinterest", "facebook"]
QUEUE_FILE = OUTPUT_DIR / "social_queue.json"

_LIMITS = {"x": 280, "threads": 500}
_X_UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"
_CHUNK_SIZE = 4 * 1024 * 1024  # 4 MB (X 청크 상한 5 MB 이하)


# ---------------------------------------------------------------------------
# 생성
# ---------------------------------------------------------------------------
def _system(platforms: list[str]) -> str:
    return (
        "You are Wehome's social media manager. Write platform-native posts for Wehome's "
        "OWN brand accounts that hook foreign K-pop fans / travelers to Korea.\n\n"
        + brand.brand_brief() + "\n"
        "Rules: native tone per platform; X <=270 chars; include Wehome naturally; add a CTA; "
        "use accurate facts only.\n"
        "Return ONLY JSON with keys for exactly these platforms: " + ", ".join(platforms) + ".\n"
        'Shapes: instagram={"caption","hashtags":[],"image_text"}, threads={"text"}, '
        'x={"text","hashtags":[]}, pinterest={"pin_title","pin_description","image_text","link"}, '
        'facebook={"text","link"}.'
    )


def generate_posts(topic: str, platforms: list[str], source: str = "") -> dict:
    src = f"\nSource/context to base posts on:\n{source}\n" if source else ""
    data = chat_json(_system(platforms), f'Topic: "{topic}".{src}')
    if data is None:
        data = {p: _offline(p, topic) for p in platforms}
        data["_mode"] = "offline-skeleton"
    else:
        data["_mode"] = "llm"
    return data


def _offline(p: str, topic: str) -> dict:
    note = "[DRAFT — set OPENAI_API_KEY]"
    base = f"{note} {topic} — Wehome, your home in Korea. (government-authorized)"
    return {
        "instagram": {"caption": base, "hashtags": ["#wehome", "#korea"], "image_text": topic[:30]},
        "threads": {"text": base},
        "x": {"text": base[:260], "hashtags": ["#wehome", "#korea"]},
        "pinterest": {"pin_title": topic[:90], "pin_description": base,
                      "image_text": "Stay legally in Korea", "link": "https://www.wehome.me"},
        "facebook": {"text": base, "link": "https://www.wehome.me"},
    }[p]


def _add_tags(text: str, tags: list[str]) -> str:
    """이미 본문에 있는 해시태그는 중복으로 붙이지 않는다."""
    low = text.lower()
    extra = " ".join(dict.fromkeys(t for t in tags if t.lower() not in low))
    return (text + (" " + extra if extra else "")).strip()


def generate_and_queue(topic: str, platforms: list[str] | None = None, source: str = "") -> list[dict]:
    """주제 → 플랫폼별 글 생성 → 검수 → 예약큐 적재 (대시보드 '글 생성' 버튼용)."""
    from . import governance
    platforms = platforms or PLATFORMS
    posts = generate_posts(topic, platforms, source)
    created = []
    for p in platforms:
        post = posts.get(p)
        if not post:
            continue
        text = render(p, post)
        rep = governance.review({"_kind": "social", "topic": topic, "platform": p}, text)
        item = enqueue(p, topic, post, rep["status"], None)
        created.append({"platform": p, "id": item["id"], "governance": rep["status"]})
    return created


def render(platform: str, post: dict) -> str:
    if platform == "x":
        return _add_tags(post.get("text", ""), post.get("hashtags", []))
    if platform == "instagram":
        return (_add_tags(post.get("caption", ""), post.get("hashtags", []))
                + f"\n[image text: {post.get('image_text','')}]").strip()
    if platform == "threads":
        return post.get("text", "")
    if platform == "pinterest":
        return f"{post.get('pin_title','')}\n{post.get('pin_description','')}\n→ {post.get('link','')}"
    if platform == "facebook":
        return f"{post.get('text','')}\n→ {post.get('link','')}"
    return json.dumps(post, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 큐 (예약·승인)
# ---------------------------------------------------------------------------
def _load() -> list[dict]:
    return json.loads(QUEUE_FILE.read_text(encoding="utf-8")) if QUEUE_FILE.exists() else []


def _save(items: list[dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    QUEUE_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def enqueue(platform: str, topic: str, post: dict, governance: str,
            scheduled_at: str | None, video_path: str | None = None) -> dict:
    items = _load()
    post = utm.inject(platform, post, topic)   # UTM 링크 자동 주입
    item = {
        "id": f"sp-{datetime.datetime.now():%Y%m%d%H%M%S%f}-{platform}",
        "platform": platform, "topic": topic, "post": post,
        "text": render(platform, post),
        "governance": governance, "status": "DRAFT",
        "scheduled_at": scheduled_at,
        "created_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "posted_at": None, "result": None,
        "video_path": video_path,
    }
    items.append(item)
    _save(items)
    _alog.append("generate", f"{platform.upper()} 콘텐츠 자동 생성", platform=platform, detail=topic[:80])
    return item


def queue() -> list[dict]:
    return _load()


def approve(item_id: str) -> dict:
    items = _load()
    for it in items:
        if it["id"] == item_id:
            if it["governance"] == "FAIL":
                return {"ok": False, "msg": "검수 FAIL 상태라 승인 불가."}
            it["status"] = "APPROVED"
            _save(items)
            return {"ok": True, "msg": f"✅ 승인됨: {item_id}"}
    return {"ok": False, "msg": f"{item_id} 없음"}


def publish_one(item_id: str) -> dict:
    """단건 즉시 게시(대시보드 '지금 게시' 버튼용). 클릭 = 승인 + 게시.
    검수 FAIL은 게시 차단. 토큰 없으면 dry-run 반환."""
    items = _load()
    for it in items:
        if it["id"] == item_id:
            if it["status"] == "POSTED":
                return {"status": "posted", "id": it.get("post", {}).get("id"), "note": "이미 게시됨"}
            if it["governance"] == "FAIL":
                return {"status": "error", "error": "검수 FAIL — 게시 불가"}
            it["status"] = "APPROVED"
            video_path = it.get("video_path")
            res = post_to(it["platform"], it["post"], video_path=video_path)
            it["result"] = res
            if res.get("status") == "posted":
                it["status"] = "POSTED"
                it["posted_at"] = datetime.datetime.now().isoformat(timespec="seconds")
            _save(items)
            return res
    return {"status": "error", "error": f"{item_id} 없음"}


def publish(due_only: bool = False) -> list[dict]:
    """APPROVED 항목을 게시(실제 or dry-run). due_only면 예약시간 도래분만."""
    items = _load()
    results = []
    for it in items:
        if it["status"] != "APPROVED":
            continue
        if due_only and it.get("scheduled_at") and not _sched.is_due(it["scheduled_at"]):
            continue
        video_path = it.get("video_path")
        res = post_to(it["platform"], it["post"], video_path=video_path)
        it["result"] = res
        if res.get("status") == "posted":
            it["status"] = "POSTED"
            it["posted_at"] = now
            _alog.append("post", f"{it['platform'].upper()} 자동 게시 완료", platform=it["platform"], detail=it.get("topic", "")[:80])
        results.append({"id": it["id"], "platform": it["platform"], **res})
    _save(items)
    return results


# ---------------------------------------------------------------------------
# HTTP 헬퍼
# ---------------------------------------------------------------------------
def _http(url: str, data: bytes, headers: dict) -> dict:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code} {e.reason}: {body}") from e


def _http_raw(url: str, data: bytes, headers: dict, method: str = "POST") -> dict:
    """응답 없는(204) 경우도 처리. 에러 시 HTTPError 상세 포함."""
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = r.read()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read()
        raise RuntimeError(f"HTTP {e.code}: {body.decode('utf-8', errors='replace')}")


def _http_get(url: str, headers: dict) -> dict:
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# OAuth 1.0a
# ---------------------------------------------------------------------------
def _pe(s) -> str:
    """RFC3986 퍼센트 인코딩 (OAuth 1.0a 규격)."""
    return urllib.parse.quote(str(s), safe="-._~")


def _oauth1_header(method: str, url: str) -> str:
    """JSON 바디용 — oauth_* 파라미터만 서명 (바디는 서명 제외)."""
    return _oauth1_sign(method, url)


def _oauth1_sign(method: str, url: str, extra_params: dict | None = None) -> str:
    """OAuth 1.0a 서명. extra_params(form/query 파라미터)를 서명에 포함."""
    oauth = {
        "oauth_consumer_key": settings.x_api_key,
        "oauth_token": settings.x_access_token,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_nonce": secrets.token_hex(16),
        "oauth_version": "1.0",
    }
    all_params = {**oauth, **(extra_params or {})}
    enc = "&".join(f"{_pe(k)}={_pe(all_params[k])}" for k in sorted(all_params))
    base = "&".join([method.upper(), _pe(url), _pe(enc)])
    key = f"{_pe(settings.x_api_secret)}&{_pe(settings.x_access_secret)}"
    oauth["oauth_signature"] = base64.b64encode(
        hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    return "OAuth " + ", ".join(f'{_pe(k)}="{_pe(v)}"' for k, v in oauth.items())


# ---------------------------------------------------------------------------
# X 영상 청크 업로드 (INIT → APPEND → FINALIZE → STATUS poll)
# ---------------------------------------------------------------------------
def _build_multipart(boundary: str, fields: dict, file_data: bytes) -> bytes:
    """Twitter media APPEND용 multipart/form-data body."""
    buf = b""
    for k, v in fields.items():
        buf += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{k}"\r\n\r\n'
            f"{v}\r\n"
        ).encode()
    buf += (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="media"; filename="chunk"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()
    return buf


def _upload_video_x(video_path: str) -> str:
    """X(Twitter) 영상 청크 업로드. 완료 후 media_id_string 반환."""
    size = os.path.getsize(video_path)

    # INIT
    init_p = {
        "command": "INIT",
        "total_bytes": str(size),
        "media_type": "video/mp4",
        "media_category": "tweet_video",
    }
    auth = _oauth1_sign("POST", _X_UPLOAD_URL, init_p)
    resp = _http_raw(_X_UPLOAD_URL, urllib.parse.urlencode(init_p).encode(), {
        "Authorization": auth,
        "Content-Type": "application/x-www-form-urlencoded",
    })
    media_id = resp["media_id_string"]
    print(f"  [X 업로드] INIT — media_id={media_id}")

    # APPEND
    with open(video_path, "rb") as f:
        idx = 0
        while True:
            chunk = f.read(_CHUNK_SIZE)
            if not chunk:
                break
            boundary = secrets.token_hex(16)
            fields = {"command": "APPEND", "media_id": media_id, "segment_index": str(idx)}
            body = _build_multipart(boundary, fields, chunk)
            # multipart APPEND: oauth_* 파라미터만 서명 (바이너리 바디 제외)
            auth = _oauth1_sign("POST", _X_UPLOAD_URL)
            _http_raw(_X_UPLOAD_URL, body, {
                "Authorization": auth,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
            })
            print(f"  [X 업로드] APPEND segment={idx} ({len(chunk)//1024}KB)")
            idx += 1

    # FINALIZE
    fin_p = {"command": "FINALIZE", "media_id": media_id}
    auth = _oauth1_sign("POST", _X_UPLOAD_URL, fin_p)
    resp = _http_raw(_X_UPLOAD_URL, urllib.parse.urlencode(fin_p).encode(), {
        "Authorization": auth,
        "Content-Type": "application/x-www-form-urlencoded",
    })
    print(f"  [X 업로드] FINALIZE — processing_info={resp.get('processing_info')}")

    # STATUS poll (비동기 처리 대기)
    proc = resp.get("processing_info", {})
    while proc.get("state") in ("pending", "in_progress"):
        wait = max(proc.get("check_after_secs", 5), 3)
        print(f"  [X 업로드] STATUS {proc.get('state')} — {wait}초 대기…")
        time.sleep(wait)
        qs = urllib.parse.urlencode({"command": "STATUS", "media_id": media_id})
        status_p = {"command": "STATUS", "media_id": media_id}
        auth = _oauth1_sign("GET", _X_UPLOAD_URL, status_p)
        resp = _http_get(f"{_X_UPLOAD_URL}?{qs}", {"Authorization": auth})
        proc = resp.get("processing_info", {})

    if proc.get("state") == "failed":
        raise RuntimeError(f"X 영상 처리 실패: {proc.get('error', proc)}")

    print(f"  [X 업로드] 완료 media_id={media_id}")
    return media_id


# ---------------------------------------------------------------------------
# Facebook 토큰 자동 갱신
# ---------------------------------------------------------------------------
def _fb_update_env(key: str, value: str) -> None:
    """실행 중 .env 파일의 특정 키를 교체하고 현재 프로세스 환경변수도 갱신."""
    import re as _re
    env_path = __import__("pathlib").Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return
    content = env_path.read_text()
    if f"{key}=" in content:
        content = _re.sub(rf"^{key}=.*", f"{key}={value}", content, flags=_re.MULTILINE)
    else:
        content += f"\n{key}={value}"
    env_path.write_text(content)
    os.environ[key] = value


def _fb_exchange_longlived(short_token: str) -> str:
    """단기 User 토큰 → 60일 장기 User 토큰. App ID+Secret 필요."""
    if not (settings.fb_app_id and settings.fb_app_secret):
        return short_token
    qs = urllib.parse.urlencode({
        "grant_type": "fb_exchange_token",
        "client_id": settings.fb_app_id,
        "client_secret": settings.fb_app_secret,
        "fb_exchange_token": short_token,
    })
    try:
        with urllib.request.urlopen(
            f"https://graph.facebook.com/v21.0/oauth/access_token?{qs}", timeout=15
        ) as r:
            data = json.loads(r.read().decode())
        long_token = data["access_token"]
        print(f"  [FB] 단기→장기 User 토큰 교환 완료 (type={data.get('token_type')})")
        return long_token
    except Exception as e:
        print(f"  [FB] 장기 토큰 교환 실패: {e}")
        return short_token


def _fb_refresh_page_token() -> str | None:
    """META_ACCESS_TOKEN으로 /me/accounts에서 Page 토큰 재발급.
    App Secret이 있으면 먼저 장기 User 토큰으로 교환 → 반영구 Page 토큰.
    성공 시 .env 자동 갱신 후 새 토큰 반환."""
    user_token = settings.meta_access_token
    if not user_token:
        return None
    # App Secret 있으면 장기 토큰 교환 시도
    if settings.fb_app_id and settings.fb_app_secret:
        user_token = _fb_exchange_longlived(user_token)
        # 장기 user 토큰도 .env에 저장
        _fb_update_env("META_ACCESS_TOKEN", user_token)
        settings.__class__.meta_access_token = user_token  # type: ignore[attr-defined]
    try:
        qs = urllib.parse.urlencode({"access_token": user_token})
        with urllib.request.urlopen(
            f"https://graph.facebook.com/v21.0/me/accounts?{qs}", timeout=15
        ) as r:
            pages = json.loads(r.read().decode()).get("data", [])
    except Exception as e:
        print(f"  [FB] /me/accounts 실패: {e}")
        return None
    page = next((p for p in pages if p["id"] == settings.fb_page_id), pages[0] if pages else None)
    if not page:
        return None
    new_token = page["access_token"]
    _fb_update_env("FB_PAGE_TOKEN", new_token)
    settings.__class__.fb_page_token = new_token  # type: ignore[attr-defined]
    print(f"  [FB] Page 토큰 자동 갱신 완료 (페이지: {page.get('name')})")
    return new_token


# ---------------------------------------------------------------------------
# Facebook 영상 직접 업로드
# ---------------------------------------------------------------------------
def _upload_video_facebook(post: dict, video_path: str) -> dict:
    """graph-video.facebook.com 멀티파트 업로드."""
    filename = os.path.basename(video_path)
    with open(video_path, "rb") as f:
        video_data = f.read()

    description = post.get("text", "")
    boundary = secrets.token_hex(16)

    buf = b""
    token = settings.fb_page_token or settings.meta_access_token
    for name, value in [
        ("description", description),
        ("access_token", token),
    ]:
        buf += (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n"
        ).encode()
    buf += (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="source"; filename="{filename}"\r\n'
        f"Content-Type: video/mp4\r\n\r\n"
    ).encode() + video_data + f"\r\n--{boundary}--\r\n".encode()

    url = f"https://graph-video.facebook.com/v21.0/{settings.fb_page_id}/videos"
    req = urllib.request.Request(url, data=buf, headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}"
    }, method="POST")
    print(f"  [FB 업로드] {filename} ({len(video_data)//1024}KB) 전송 중…")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            out = json.loads(r.read().decode())
        print(f"  [FB 업로드] 완료 id={out.get('id')}")
        return {"status": "posted", "id": out.get("id"), "api": out}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"FB 영상 업로드 실패 HTTP {e.code}: {body}") from e


# ---------------------------------------------------------------------------
# 플랫폼 커넥터 (자격증명 있으면 실제, 없으면 dry-run)
# ---------------------------------------------------------------------------
def post_to(platform: str, post: dict, video_path: str | None = None) -> dict:
    try:
        return _CONNECTORS[platform](post, video_path=video_path)
    except Exception as e:
        return {"status": "error", "error": str(e)}


def _dry(platform: str, post: dict, reason: str) -> dict:
    return {"status": "dry-run", "reason": reason, "preview": render(platform, post)}


def _wehome_image() -> str:
    """게시할 이미지 URL이 없을 때 위홈 홈페이지 공개 이미지로 폴백."""
    try:
        from . import wehome_images
        return wehome_images.pick_image()
    except Exception:
        return ""


def _post_x(post: dict, video_path: str | None = None) -> dict:
    url = "https://api.twitter.com/2/tweets"
    body_dict: dict = {"text": render("x", post)}

    # 영상 업로드 (OAuth1.0a 필수)
    if video_path and os.path.exists(video_path) and settings.x_oauth1_enabled:
        try:
            media_id = _upload_video_x(video_path)
            body_dict["media"] = {"media_ids": [media_id]}
        except Exception as e:
            print(f"⚠️ X 영상 업로드 실패 (텍스트만 게시): {e}")

    body = json.dumps(body_dict).encode()
    if settings.x_oauth1_enabled:
        headers = {"Authorization": _oauth1_header("POST", url),
                   "Content-Type": "application/json"}
    elif settings.x_bearer_token:
        headers = {"Authorization": f"Bearer {settings.x_bearer_token}",
                   "Content-Type": "application/json"}
    else:
        return _dry("x", post, "X 자격증명 없음 (OAuth1.0a 4종 또는 X_BEARER_TOKEN)")
    out = _http(url, body, headers)
    return {"status": "posted", "id": out.get("data", {}).get("id"), "api": out}


def _post_facebook(post: dict, video_path: str | None = None) -> dict:
    token = settings.fb_page_token or settings.meta_access_token  # Page 토큰 우선
    if not (token and settings.fb_page_id):
        return _dry("facebook", post, "FB_PAGE_TOKEN(또는 META_ACCESS_TOKEN)/FB_PAGE_ID 없음")

    def _do_post(tok: str) -> dict:
        if video_path and os.path.exists(video_path):
            try:
                return _upload_video_facebook(post, video_path)
            except Exception as e:
                print(f"⚠️ FB 영상 업로드 실패 → 텍스트로 게시: {e}")
        params = {"message": post.get("text", ""), "access_token": tok}
        if post.get("link"):
            params["link"] = post["link"]
        out = _http(f"https://graph.facebook.com/v21.0/{settings.fb_page_id}/feed",
                    urllib.parse.urlencode(params).encode(),
                    {"Content-Type": "application/x-www-form-urlencoded"})
        return {"status": "posted", "id": out.get("id"), "api": out}

    try:
        return _do_post(token)
    except RuntimeError as e:
        # 토큰 만료(code 190)면 자동 재발급 후 1회 재시도
        if "190" in str(e):
            print(f"⚠️ FB 토큰 만료 감지 — 자동 갱신 시도…")
            new_token = _fb_refresh_page_token()
            if new_token:
                return _do_post(new_token)
        raise


def _upload_to_catbox(video_path: str) -> str:
    """catbox.moe에 영상 업로드 → 공개 URL 반환. 추가 설정 불필요."""
    filename = os.path.basename(video_path)
    with open(video_path, "rb") as f:
        video_data = f.read()
    boundary = secrets.token_hex(16)
    buf = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="reqtype"\r\n\r\n'
        f"fileupload\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="fileToUpload"; filename="{filename}"\r\n'
        f"Content-Type: video/mp4\r\n\r\n"
    ).encode() + video_data + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        "https://catbox.moe/user/api.php", data=buf,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    print(f"  [Threads] 공개 호스팅 업로드 중 ({len(video_data)//1024}KB)…")
    with urllib.request.urlopen(req, timeout=120) as r:
        url = r.read().decode().strip()
    if not url.startswith("https://"):
        raise RuntimeError(f"catbox 업로드 실패: {url}")
    print(f"  [Threads] 공개 URL: {url}")
    return url


def _post_threads(post: dict, video_path: str | None = None) -> dict:
    token = settings.threads_access_token or settings.meta_access_token
    if not (token and settings.threads_user_id):
        return _dry("threads", post, "META_ACCESS_TOKEN_THREADS/THREADS_USER_ID 없음")
    base = f"https://graph.threads.net/v1.0/{settings.threads_user_id}"
    text = post.get("text", "")

    # 영상이 있으면 공개 URL로 올려서 VIDEO 컨테이너 생성
    if video_path and os.path.exists(video_path):
        try:
            video_url = _upload_to_catbox(video_path)
            print(f"  [Threads] VIDEO 컨테이너 생성 중…")
            create = _http(f"{base}/threads",
                           urllib.parse.urlencode({
                               "media_type": "VIDEO",
                               "video_url": video_url,
                               "text": text,
                               "access_token": token,
                           }).encode(),
                           {"Content-Type": "application/x-www-form-urlencoded"})
            cid = create.get("id")
            # 처리 완료 대기 (최대 60초)
            for _ in range(12):
                time.sleep(5)
                status_resp = _http_get(
                    f"https://graph.threads.net/v1.0/{cid}?fields=status,error_message&access_token={token}",
                    {}
                )
                st = status_resp.get("status", "")
                print(f"  [Threads] 영상 처리 상태: {st}")
                if st == "FINISHED":
                    break
                if st == "ERROR":
                    raise RuntimeError(f"Threads 영상 처리 실패: {status_resp.get('error_message')}")
        except Exception as e:
            print(f"⚠️ Threads 영상 업로드 실패 → 텍스트로 게시: {e}")
            cid = None

        if cid:
            pub = _http(f"{base}/threads_publish",
                        urllib.parse.urlencode({"creation_id": cid, "access_token": token}).encode(),
                        {"Content-Type": "application/x-www-form-urlencoded"})
            return {"status": "posted", "id": pub.get("id"), "api": pub}

    # 텍스트 게시
    create = _http(f"{base}/threads",
                   urllib.parse.urlencode({"media_type": "TEXT", "text": text,
                                           "access_token": token}).encode(),
                   {"Content-Type": "application/x-www-form-urlencoded"})
    cid = create.get("id")
    pub = _http(f"{base}/threads_publish",
                urllib.parse.urlencode({"creation_id": cid, "access_token": token}).encode(),
                {"Content-Type": "application/x-www-form-urlencoded"})
    return {"status": "posted", "id": pub.get("id"), "api": pub}


def _post_instagram(post: dict, video_path: str | None = None) -> dict:
    token = settings.meta_access_token
    if not (token and settings.ig_user_id):
        return _dry("instagram", post, "META_ACCESS_TOKEN/IG_USER_ID 없음")
    base = f"https://graph.facebook.com/v21.0/{settings.ig_user_id}"
    cap = _add_tags(post.get("caption", ""), post.get("hashtags", []))

    # 영상 → Reels 업로드
    if video_path and os.path.exists(video_path):
        try:
            video_url = _upload_to_catbox(video_path)
            print(f"  [IG] Reels 컨테이너 생성 중…")
            cont = _http(f"{base}/media",
                         urllib.parse.urlencode({
                             "media_type": "REELS",
                             "video_url": video_url,
                             "caption": cap,
                             "access_token": token,
                         }).encode(),
                         {"Content-Type": "application/x-www-form-urlencoded"})
            cid = cont.get("id")
            # 처리 완료 대기 (최대 90초)
            for _ in range(18):
                time.sleep(5)
                st_resp = _http_get(
                    f"https://graph.facebook.com/v21.0/{cid}?fields=status_code&access_token={token}", {}
                )
                st = st_resp.get("status_code", "")
                print(f"  [IG] 영상 처리 상태: {st}")
                if st == "FINISHED":
                    break
                if st == "ERROR":
                    raise RuntimeError(f"IG 영상 처리 실패: {st_resp}")
            pub = _http(f"{base}/media_publish",
                        urllib.parse.urlencode({"creation_id": cid, "access_token": token}).encode(),
                        {"Content-Type": "application/x-www-form-urlencoded"})
            return {"status": "posted", "id": pub.get("id"), "api": pub}
        except Exception as e:
            print(f"⚠️ IG 영상 업로드 실패 → 이미지로 폴백 시도: {e}")

    # 이미지 게시 (image_url 없으면 위홈 홈페이지 이미지로 자동 폴백)
    image_url = post.get("image_url") or _wehome_image()
    if image_url:
        cont = _http(f"{base}/media",
                     urllib.parse.urlencode({"image_url": image_url, "caption": cap,
                                             "access_token": token}).encode(),
                     {"Content-Type": "application/x-www-form-urlencoded"})
        pub = _http(f"{base}/media_publish",
                    urllib.parse.urlencode({"creation_id": cont.get("id"),
                                            "access_token": token}).encode(),
                    {"Content-Type": "application/x-www-form-urlencoded"})
        return {"status": "posted", "id": pub.get("id"), "api": pub}

    return _dry("instagram", post, "영상/이미지 없음 — video_path 또는 post.image_url 필요")


def _post_pinterest(post: dict, video_path: str | None = None) -> dict:
    if not (settings.pinterest_token and settings.pinterest_board_id):
        return _dry("pinterest", post, "PINTEREST_TOKEN/BOARD_ID 없음")
    # image_url 없으면 위홈 홈페이지 이미지로 자동 폴백
    image_url = post.get("image_url") or _wehome_image()
    if not image_url:
        return _dry("pinterest", post, "이미지 URL 필요(post.image_url)")
    body = json.dumps({
        "board_id": settings.pinterest_board_id,
        "title": post.get("pin_title", ""), "description": post.get("pin_description", ""),
        "link": post.get("link", ""),
        "media_source": {"source_type": "image_url", "url": image_url},
    }).encode()
    out = _http("https://api.pinterest.com/v5/pins", body,
                {"Authorization": f"Bearer {settings.pinterest_token}",
                 "Content-Type": "application/json"})
    return {"status": "posted", "id": out.get("id"), "api": out}


def _youtube_refresh_access_token() -> str:
    """refresh_token으로 새 access_token 발급 후 .env 갱신."""
    data = urllib.parse.urlencode({
        "client_id": settings.youtube_client_id,
        "client_secret": settings.youtube_client_secret,
        "refresh_token": settings.youtube_refresh_token,
        "grant_type": "refresh_token",
    }).encode()
    with urllib.request.urlopen(
        urllib.request.Request("https://oauth2.googleapis.com/token", data=data,
                               headers={"Content-Type": "application/x-www-form-urlencoded"}),
        timeout=15
    ) as r:
        token = json.loads(r.read().decode())["access_token"]
    _fb_update_env("YOUTUBE_ACCESS_TOKEN", token)
    settings.__class__.youtube_access_token = token  # type: ignore[attr-defined]
    return token


def _post_youtube(post: dict, video_path: str | None = None) -> dict:
    if not (settings.youtube_refresh_token and settings.youtube_client_id):
        return _dry("youtube", post, "YOUTUBE_REFRESH_TOKEN/CLIENT_ID 없음")
    if not (video_path and os.path.exists(video_path)):
        return _dry("youtube", post, "영상 파일 필요 (YouTube Shorts는 영상 전용)")

    token = settings.youtube_access_token or _youtube_refresh_access_token()

    with open(video_path, "rb") as f:
        video_data = f.read()

    text = post.get("text", "") or post.get("caption", "")
    metadata = json.dumps({
        "snippet": {
            "title": f"{text[:90]} #Shorts" if "#Shorts" not in text else text[:97],
            "description": f"{text}\n\n#wehome #korea #숙소 #Shorts",
            "tags": ["wehome", "위홈", "한국숙소", "Shorts"],
            "categoryId": "19",
        },
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False},
    }).encode()

    def _upload(tok: str) -> dict:
        with urllib.request.urlopen(
            urllib.request.Request(
                "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
                data=metadata,
                headers={
                    "Authorization": f"Bearer {tok}",
                    "Content-Type": "application/json",
                    "X-Upload-Content-Type": "video/mp4",
                    "X-Upload-Content-Length": str(len(video_data)),
                }, method="POST"
            ), timeout=30
        ) as r:
            upload_url = r.headers["Location"]
        print(f"  [YouTube] 업로드 중 ({len(video_data)//1024}KB)…")
        with urllib.request.urlopen(
            urllib.request.Request(upload_url, data=video_data, headers={
                "Content-Type": "video/mp4",
                "Content-Length": str(len(video_data)),
            }, method="PUT"), timeout=180
        ) as r:
            return json.loads(r.read().decode())

    try:
        result = _upload(token)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            print("  [YouTube] 토큰 만료 → 자동 갱신 후 재시도…")
            token = _youtube_refresh_access_token()
            result = _upload(token)
        else:
            raise

    vid_id = result.get("id")
    print(f"  [YouTube] 완료 → https://www.youtube.com/shorts/{vid_id}")
    return {"status": "posted", "id": vid_id, "url": f"https://www.youtube.com/shorts/{vid_id}", "api": result}


_CONNECTORS = {
    "x": _post_x, "facebook": _post_facebook, "threads": _post_threads,
    "instagram": _post_instagram, "pinterest": _post_pinterest,
    "youtube": _post_youtube,
}


def connection_status() -> list[dict]:
    """게시 없이 각 플랫폼 연결 상태(토큰 유무)만 점검."""
    s = settings

    def row(platform, ready, note=""):
        return {"platform": platform, "ready": ready,
                "mode": "실게시 가능" if ready else "dry-run", "note": note}

    x_ready = s.x_oauth1_enabled or bool(s.x_bearer_token)
    x_note = ("OAuth1.0a 정적(안정)" if s.x_oauth1_enabled
              else ("Bearer(만료형)" if s.x_bearer_token else "토큰 없음"))
    meta = bool(s.meta_access_token)
    return [
        row("x", x_ready, x_note),
        row("facebook", meta and bool(s.fb_page_id),
            "" if (meta and s.fb_page_id) else "META_ACCESS_TOKEN/FB_PAGE_ID 필요"),
        row("threads", meta and bool(s.threads_user_id),
            "" if (meta and s.threads_user_id) else "META_ACCESS_TOKEN/THREADS_USER_ID 필요"),
        row("instagram", meta and bool(s.ig_user_id),
            "+ 이미지 URL 필요" if (meta and s.ig_user_id) else "META_ACCESS_TOKEN/IG_USER_ID 필요"),
        row("pinterest", bool(s.pinterest_token and s.pinterest_board_id),
            "+ 이미지 URL 필요" if (s.pinterest_token and s.pinterest_board_id)
            else "PINTEREST_TOKEN/BOARD_ID 필요"),
    ]
