"""Reddit 기회 레이더 + 초안 도우미 (사람이 직접 게시).

⚠️ 이 모듈은 절대 자동 게시하지 않는다. Reddit 약관상 자동 댓글/게시·카르마
파밍은 금지(스팸/조작)이며 브랜드에 치명적이다. 여기서 하는 일은:
  1) 공개 검색 API(읽기 전용)로 최근 관련 스레드를 찾고
  2) 각 스레드에 맞는 '진짜 도움되는' 답변 초안을 생성(디스클로저 포함)
  3) 사람이 대시보드에서 검토 → 복사 → 본인이 직접 게시
순수 도움 답변(위홈 미언급)을 기본으로 하고, 위홈 언급은 디스클로저를 단
선택 문단으로만 제공(9:1 규칙 권장).
"""
from __future__ import annotations

import base64
import json
import urllib.parse
import urllib.request

from . import brand
from .config import settings
from .generator import TODAY, slugify
from .llm import chat_json

SUBREDDITS = ["koreatravel", "seoul", "Living_in_Korea"]
# 위홈과 관련 높은 여행자 질문 의도 (검색어)
QUERY = '"where to stay" OR airbnb OR accommodation OR "long stay" OR "pet friendly"'
UA = "wehome-radar/0.1 (read-only opportunity research)"

_token_cache: dict[str, str] = {}


def _bearer() -> str | None:
    """Reddit 공식 API용 app-only 토큰 (client_credentials)."""
    if not settings.reddit_enabled:
        return None
    if "tok" in _token_cache:
        return _token_cache["tok"]
    auth = base64.b64encode(
        f"{settings.reddit_client_id}:{settings.reddit_client_secret}".encode()).decode()
    body = urllib.parse.urlencode({"grant_type": "client_credentials"}).encode()
    req = urllib.request.Request(
        "https://www.reddit.com/api/v1/access_token", data=body,
        headers={"Authorization": f"Basic {auth}", "User-Agent": UA})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.loads(r.read().decode("utf-8"))
    tok = data.get("access_token")
    if not tok:
        print(f"[Reddit] 토큰 발급 실패: {data}")
        return None
    _token_cache["tok"] = tok
    return tok


def _get_json(url: str) -> dict | None:
    try:
        headers = {"User-Agent": UA}
        tok = _bearer()
        if tok:
            headers["Authorization"] = f"bearer {tok}"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:
        print(f"⚠️ Reddit 검색 실패({e})")
        return None


def find_opportunities(per_sub: int = 8) -> list[dict] | None:
    """최근(한 달 내) 관련 스레드를 모아 반환. 네트워크 실패 시 None.
    REDDIT_CLIENT_ID/SECRET 설정 시 공식 API(oauth.reddit.com), 아니면 비인증 폴백."""
    base = "https://oauth.reddit.com" if settings.reddit_enabled else "https://www.reddit.com"
    found: dict[str, dict] = {}
    any_ok = False
    for sub in SUBREDDITS:
        url = (f"{base}/r/{sub}/search?" if settings.reddit_enabled
               else f"{base}/r/{sub}/search.json?")
        url += urllib.parse.urlencode({"q": QUERY, "restrict_sr": "on",
                                       "sort": "new", "t": "month", "limit": per_sub})
        data = _get_json(url)
        if data is None:
            continue
        any_ok = True
        for ch in data.get("data", {}).get("children", []):
            d = ch.get("data", {})
            perma = d.get("permalink", "")
            if not perma:
                continue
            found[perma] = {
                "title": d.get("title", ""),
                "subreddit": d.get("subreddit", sub),
                "url": "https://www.reddit.com" + perma,
                "num_comments": d.get("num_comments", 0),
                "score": d.get("score", 0),
                "created_utc": d.get("created_utc", 0),
                "selftext": (d.get("selftext", "") or "")[:600],
            }
    if not any_ok:
        return None
    # 최신순 정렬
    return sorted(found.values(), key=lambda x: -x["created_utc"])


# ---------------------------------------------------------------------------
# 초안 생성
# ---------------------------------------------------------------------------
_SYSTEM = (
    "You help a Wehome team member participate AUTHENTICALLY and helpfully on Reddit "
    "(r/koreatravel etc.). Reddit removes ads and self-promo, so your job is to write a "
    "genuinely useful, human reply to the specific thread — value first, no hype, no "
    "'book now'.\n\n" + brand.brand_brief() + "\n"
    "Write TWO things:\n"
    "1) reply: a helpful, specific answer to THIS thread. By default mention NO brand "
    "(pure value — this builds trust and fits the 9:1 rule). Use accurate facts only.\n"
    "2) optional_wehome_line: ONE optional sentence the human MAY append, honestly "
    "mentioning Wehome as the government-authorized option, and it MUST contain an explicit "
    "disclosure like 'Disclosure: I work with Wehome.'\n"
    "Return ONLY JSON: {\"reply\":\"...\",\"optional_wehome_line\":\"...\",\"rules_note\":\"short reminder to follow the subreddit's rules and not paste identical text\"}"
)


def draft_for(thread: dict) -> dict:
    user = (f"Subreddit: r/{thread['subreddit']}\nThread title: {thread['title']}\n"
            f"Thread body: {thread['selftext']}\n\nWrite the reply.")
    data = chat_json(_SYSTEM, user)
    if data is None:
        data = {"reply": "[DRAFT — set OPENAI_API_KEY] " + brand.KEY_FACTS[1],
                "optional_wehome_line": ("Disclosure: I work with Wehome, Korea's "
                                         "government-authorized home-sharing platform."),
                "rules_note": "Follow the subreddit rules; vary wording; 9:1."}
        data["_mode"] = "offline-skeleton"
    else:
        data["_mode"] = "llm"
    data["_kind"] = "reddit-reply"
    data["topic"] = thread["title"]
    data["thread_url"] = thread["url"]
    data["subreddit"] = thread["subreddit"]
    data["slug"] = slugify(thread["title"]) + "-reddit-reply"
    data["generated_at"] = TODAY
    return data


def render_markdown(c: dict) -> str:
    return (f"# 📄 Wehome — REDDIT 답변 초안 (사람이 직접 게시)\n\n"
            f"> 모드: {c.get('_mode')} · 생성일: {c['generated_at']} · 상태: DRAFT — 검토 후 본인이 게시\n\n"
            f"**대상 스레드:** [{c['topic']}]({c['thread_url']})  ·  r/{c['subreddit']}\n\n---\n\n"
            f"### 1) 그대로 복사할 답변 (위홈 미언급 — 안전·기본)\n\n{c.get('reply','')}\n\n"
            f"### 2) (선택) 카르마 쌓인 뒤에만, 디스클로저와 함께 한 줄 추가\n\n"
            f"> {c.get('optional_wehome_line','')}\n\n---\n\n"
            f"*⚠️ {c.get('rules_note','')}*\n"
            f"*자동 게시 아님 — 검토 후 직접 올리세요. 같은 문구 복붙 금지, 9:1 규칙.*\n")
