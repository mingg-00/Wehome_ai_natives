"""위홈 홈페이지 이미지 수집기.

Instagram·Pinterest API는 로컬 파일을 못 받고 '공개 URL'만 받는다.
위홈 공식 홈페이지(및 CDN)는 이미 공개 이미지 URL을 노출하므로,
별도 업로드 없이 그 URL을 그대로 게시 이미지로 쓴다.

- og:image  → 브랜드 대표 배너(가장 안정적, 기본값)
- image.wehome.me/* → 실제 숙소 이미지(다양성용)

네트워크 실패해도 안전하게 빈 결과/기본 이미지로 폴백한다.
"""
from __future__ import annotations

import re
import urllib.request

HOMEPAGE = "https://www.wehome.me"
# 홈페이지가 막혀도 항상 쓸 수 있는 안정적 브랜드 대표 이미지(og:image)
FALLBACK_IMAGE = "https://d1ff1mcd5ly5rr.cloudfront.net/image/banner-kr.png"

_UA = "Mozilla/5.0 (compatible; WehomeMarketingBot/1.0)"
_OG_RE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.IGNORECASE,
)
_IMG_RE = re.compile(
    r'https://image\.wehome\.me/[^\s"\'<>]+\.(?:jpg|jpeg|png|webp)',
    re.IGNORECASE,
)

# 매 게시마다 홈페이지를 다시 긁지 않도록 1회 캐시
_cache: list[str] | None = None


def _fetch_html(url: str = HOMEPAGE, timeout: int = 10) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def homepage_images(refresh: bool = False) -> list[str]:
    """위홈 홈페이지에서 공개 이미지 URL 목록을 수집한다.
    [og:image(대표 배너), 숙소 이미지들...] 순서. 실패 시 [FALLBACK_IMAGE]."""
    global _cache
    if _cache is not None and not refresh:
        return _cache
    try:
        html = _fetch_html()
        urls: list[str] = []
        og = _OG_RE.search(html)
        if og:
            urls.append(og.group(1))
        # 숙소 이미지(중복 제거, 등장 순서 유지)
        for u in _IMG_RE.findall(html):
            if u not in urls:
                urls.append(u)
        _cache = urls or [FALLBACK_IMAGE]
    except Exception as e:
        print(f"⚠️ 위홈 홈페이지 이미지 수집 실패({e}) → 기본 배너 사용")
        _cache = [FALLBACK_IMAGE]
    return _cache


def pick_image(index: int = 0) -> str:
    """게시에 쓸 공개 이미지 URL 1개. index로 다른 이미지 선택(목록 길이로 순환)."""
    imgs = homepage_images()
    if not imgs:
        return FALLBACK_IMAGE
    return imgs[index % len(imgs)]
