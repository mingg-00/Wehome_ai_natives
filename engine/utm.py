"""UTM 링크 자동 생성 — SNS 게시물 → 위홈 예약 전환 추적용."""
from __future__ import annotations

import datetime
import urllib.parse

BASE_URL = "https://www.wehome.me"

# 플랫폼별 utm_source 매핑
_SOURCE: dict[str, str] = {
    "instagram": "instagram",
    "threads":   "threads",
    "facebook":  "facebook",
    "x":         "x",
    "pinterest":  "pinterest",
    "youtube":   "youtube",
    "tiktok":    "tiktok",
}


def build(
    platform: str,
    campaign: str = "",
    content: str = "",
    path: str = "",
) -> str:
    """UTM 파라미터가 붙은 wehome.me 링크 반환.

    Args:
        platform: SNS 플랫폼 이름 (instagram, threads, ...)
        campaign: utm_campaign 값. 비우면 YYYYMM 자동 생성.
        content:  utm_content 값 (게시물 ID·주제 슬러그 등). 선택.
        path:     wehome.me 이후 경로 (예: "/rooms"). 기본은 홈.
    """
    source = _SOURCE.get(platform, platform)
    if not campaign:
        campaign = f"sns-{datetime.datetime.now():%Y%m}"

    params: dict[str, str] = {
        "utm_source":   source,
        "utm_medium":   "social",
        "utm_campaign": campaign,
    }
    if content:
        params["utm_content"] = content

    base = BASE_URL + (path if path.startswith("/") else "")
    return f"{base}?{urllib.parse.urlencode(params)}"


def inject(platform: str, post: dict, topic: str = "") -> dict:
    """post dict에 UTM 링크를 주입해 새 dict 반환 (원본 불변).

    플랫폼별 링크 필드:
        - facebook : post['link']
        - pinterest: post['link']
        - instagram : post['caption'] 말미에 \n🔗 링크 추가
        - threads   : post['text'] 말미에 추가
        - x         : post['text'] 말미에 추가 (280자 이내로 truncate)
    """
    slug = _slugify(topic)
    url = build(platform, content=slug)
    p = dict(post)  # shallow copy — 원본 보존

    if platform == "facebook":
        p["link"] = url

    elif platform == "pinterest":
        p["link"] = url

    elif platform == "instagram":
        caption = p.get("caption", "")
        if "wehome.me" not in caption:
            p["caption"] = caption + f"\n🔗 {url}"

    elif platform == "threads":
        text = p.get("text", "")
        if "wehome.me" not in text:
            p["text"] = text + f"\n🔗 {url}"

    elif platform == "x":
        text = p.get("text", "")
        if "wehome.me" not in text:
            suffix = f" {url}"
            limit = 280 - len(suffix)
            p["text"] = text[:limit] + suffix

    return p


def _slugify(text: str) -> str:
    """주제 텍스트를 utm_content용 짧은 슬러그로 변환."""
    import re
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug[:40]
