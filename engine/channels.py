"""외국인 채널 포맷 생성 (Reddit / 숏폼 / Pinterest).

블로그가 없어도 외국인이 있는 곳(영어권)에 바로 투입할 수 있는 콘텐츠를 만든다.
공통: 브랜드/검증사실/법적 가드레일(brand.py) 주입 → governance가 검수.
- reddit:    비스팸·도움 중심 답변/포스트 (정직한 위홈 언급 + 디스클로저)
- shortform: 30초 Shorts/Reels/TikTok 대본 (훅·비트·자막·CTA·해시태그)
- pinterest: 핀 제목·설명·이미지문구·키워드
"""
from __future__ import annotations

from . import brand
from .generator import TODAY, slugify
from .llm import chat_json

FORMATS = ("reddit", "shortform", "pinterest")


def _system(fmt: str) -> str:
    base = (f"You write English marketing content for Wehome targeting FOREIGN travelers "
            f"planning a trip to Korea.\n\n{brand.brand_brief()}\n")
    if fmt == "reddit":
        return base + """
Write a genuinely HELPFUL Reddit answer (subs like r/koreatravel, r/seoul). Reddit
removes ads, so it must NOT read like marketing: lead with real, useful advice; mention
Wehome honestly as the legal/government-authorized option (not a hard sell); include a
one-line honest disclosure. No "book now", no hype.
Return ONLY JSON: {"subreddits":["..."],"title":"post title","body":"markdown answer",
"disclosure":"one-line honest disclosure to add"}"""
    if fmt == "shortform":
        return base + """
Write a 30-second vertical video script (YouTube Shorts / Reels / TikTok). Strong 3-second
hook (e.g., the Airbnb-legality angle), fast beats with voiceover + on-screen text, a clear
CTA, a caption, and hashtags.
Return ONLY JSON: {"platforms":["Shorts","Reels","TikTok"],"hook":"first 3s line",
"beats":[{"time":"0-3s","voiceover":"...","on_screen":"..."}],"cta":"...","caption":"...",
"hashtags":["#..."]}"""
    # pinterest
    return base + """
Write a Pinterest pin for travel planners searching how/where to stay in Korea. Keyword-rich
title and description, short punchy image text, a board suggestion, and keywords.
Return ONLY JSON: {"pin_title":"...","pin_description":"keyword-rich 2-3 sentences",
"image_text":"short overlay text","board":"board name","keywords":["..."]}"""


def _user(fmt: str, topic: str, kw: str) -> str:
    k = f' Target keyword/angle: "{kw}".' if kw else ""
    return f'Topic: "{topic}".{k}'


def generate(topic: str, fmt: str, primary_keyword: str = "") -> dict:
    data = chat_json(_system(fmt), _user(fmt, topic, primary_keyword))
    if data is None:
        data = _offline(fmt, topic)
        data["_mode"] = "offline-skeleton"
    else:
        data["_mode"] = "llm"
    data["_kind"] = fmt
    data["topic"] = topic
    data["slug"] = f"{slugify(topic)}-{fmt}"
    data["generated_at"] = TODAY
    return data


def _offline(fmt: str, topic: str) -> dict:
    note = "[DRAFT — set OPENAI_API_KEY for full copy]"
    if fmt == "reddit":
        return {"subreddits": ["r/koreatravel", "r/seoul"], "title": topic,
                "body": f"{note}\n\n{brand.TRUST_STATEMENT_EN}",
                "disclosure": "Disclosure: I work with Wehome."}
    if fmt == "shortform":
        return {"platforms": ["Shorts", "Reels", "TikTok"],
                "hook": f"{note} Is your Korea Airbnb legal?",
                "beats": [{"time": "0-3s", "voiceover": note, "on_screen": "Wehome"}],
                "cta": "Search Wehome — your home in Korea.",
                "caption": brand.TRUST_STATEMENT_EN, "hashtags": ["#korea", "#seoul", "#wehome"]}
    return {"pin_title": topic, "pin_description": f"{note} {brand.TRUST_STATEMENT_EN}",
            "image_text": "Stay legally in Korea", "board": "Korea Travel",
            "keywords": ["where to stay korea", "seoul travel", "wehome"]}


# ---------------------------------------------------------------------------
# 게시용 마크다운 렌더
# ---------------------------------------------------------------------------
def render_markdown(c: dict) -> str:
    head = (f"# 📄 Wehome — {c['_kind'].upper()} (게시용, 자동 생성)\n\n"
            f"> 모드: {c.get('_mode')} · 생성일: {c['generated_at']} · 상태: DRAFT — 사람 승인 후 게시\n\n---\n\n")
    if c["_kind"] == "reddit":
        subs = ", ".join(c.get("subreddits", []))
        return head + (f"**추천 서브레딧:** {subs}\n\n"
                       f"**제목:** {c.get('title','')}\n\n---\n\n{c.get('body','')}\n\n---\n\n"
                       f"*{c.get('disclosure','')}*\n")
    if c["_kind"] == "shortform":
        beats = "\n".join(f"| {b.get('time','')} | {b.get('voiceover','')} | {b.get('on_screen','')} |"
                          for b in c.get("beats", []))
        tags = " ".join(c.get("hashtags", []))
        return head + (f"**플랫폼:** {', '.join(c.get('platforms', []))}\n\n"
                       f"**훅 (0-3초):** {c.get('hook','')}\n\n"
                       f"| 시간 | 보이스오버 | 화면 자막 |\n|---|---|---|\n{beats}\n\n"
                       f"**CTA:** {c.get('cta','')}\n\n**캡션:** {c.get('caption','')}\n\n**해시태그:** {tags}\n")
    # pinterest
    kw = ", ".join(c.get("keywords", []))
    return head + (f"**핀 제목:** {c.get('pin_title','')}\n\n"
                   f"**핀 설명:** {c.get('pin_description','')}\n\n"
                   f"**이미지 문구:** {c.get('image_text','')}\n\n"
                   f"**보드:** {c.get('board','')}\n\n**키워드:** {kw}\n")
