"""다국어 SNS 콘텐츠 자동 생성 — 한국어·영어·일본어 동시 생성.

같은 주제로 언어별 네이티브 톤의 포스트를 한 번에 만든다.
각 언어는 해당 타겟 시장(일본·영어권)에 맞는 해시태그와 표현을 사용한다.
"""
from __future__ import annotations

from .llm import chat_json

SUPPORTED_LANGS: dict[str, str] = {
    "ko": "Korean",
    "en": "English",
    "ja": "Japanese",
}

_LANG_RULES: dict[str, str] = {
    "ko": (
        "Write in natural Korean (한국어). "
        "Use Korean hashtags mixed with English ones. "
        "Tone: warm, trustworthy, modern."
    ),
    "en": (
        "Write in natural English targeting Western/international travelers. "
        "Hashtags in English. Tone: friendly, adventurous, inspiring."
    ),
    "ja": (
        "Write in natural Japanese (日本語) targeting Japanese travelers to Korea. "
        "Use Japanese hashtags (e.g. #韓国旅行 #ウィホーム) mixed with Korean ones. "
        "Tone: polite, warm, travel-inspiring. "
        "Japanese travelers value safety and government authorization — highlight this."
    ),
}

_PLATFORM_SHAPES = (
    'instagram={"caption","hashtags":[],"image_text"}, '
    'threads={"text"}, '
    'x={"text","hashtags":[]}, '
    'facebook={"text","link"}, '
    'pinterest={"pin_title","pin_description","image_text","link"}'
)


def _system(platforms: list[str], lang: str) -> str:
    lang_name = SUPPORTED_LANGS.get(lang, "English")
    lang_rules = _LANG_RULES.get(lang, _LANG_RULES["en"])
    return (
        f"You are Wehome's social media manager writing in {lang_name}. "
        "Wehome is a South Korean government-authorized short-term rental platform "
        "targeting foreign travelers. It is legal, safe, and verified by the Korean government.\n\n"
        f"Language rules: {lang_rules}\n\n"
        "Rules: native tone per platform; X <=270 chars; include Wehome naturally; "
        "add a clear CTA linking to wehome.me; use accurate facts only.\n"
        f"Return ONLY JSON with keys for exactly these platforms: {', '.join(platforms)}.\n"
        f"Shapes: {_PLATFORM_SHAPES}."
    )


def generate_posts_multilang(
    topic_by_lang: dict[str, str],
    platforms: list[str],
    langs: list[str] | None = None,
) -> dict[str, dict]:
    """언어별 플랫폼 포스트 생성.

    Args:
        topic_by_lang: {"ko": "한국어 주제", "en": "English topic", "ja": "日本語トピック"}
                       언어별로 다른 주제 문구 지원. 없으면 "ko" fallback.
        platforms:     포스팅할 플랫폼 목록.
        langs:         생성할 언어 목록. None이면 SUPPORTED_LANGS 전체.

    Returns:
        {"ko": {platform: post_dict}, "en": {...}, "ja": {...}}
    """
    langs = langs or list(SUPPORTED_LANGS.keys())
    result: dict[str, dict] = {}

    for lang in langs:
        topic = topic_by_lang.get(lang) or topic_by_lang.get("ko", "")
        data = chat_json(_system(platforms, lang), f'Topic: "{topic}".')
        if data is None:
            data = {p: _offline(p, topic, lang) for p in platforms}
            data["_mode"] = "offline"
        else:
            data["_mode"] = "llm"
        result[lang] = data

    return result


def _offline(platform: str, topic: str, lang: str) -> dict:
    """LLM 없을 때 언어별 기본 스켈레톤."""
    templates = {
        "ko": f"[초안] {topic} — 위홈, 정부인증 한국 숙소.",
        "en": f"[DRAFT] {topic} — Wehome, government-authorized stays in Korea.",
        "ja": f"[下書き] {topic} — Wehome、韓国政府公認の宿泊施設。",
    }
    base = templates.get(lang, templates["en"])
    tags_map = {
        "ko": ["#위홈", "#한국여행"],
        "en": ["#Wehome", "#KoreaTravel"],
        "ja": ["#ウィホーム", "#韓国旅行"],
    }
    tags = tags_map.get(lang, tags_map["en"])
    return {
        "instagram": {"caption": base, "hashtags": tags, "image_text": topic[:30]},
        "threads":   {"text": base},
        "x":         {"text": base[:260], "hashtags": tags},
        "facebook":  {"text": base, "link": "https://www.wehome.me"},
        "pinterest": {"pin_title": topic[:90], "pin_description": base,
                      "image_text": topic[:30], "link": "https://www.wehome.me"},
    }.get(platform, {"text": base})


def flatten_for_queue(
    multilang_posts: dict[str, dict],
    platforms: list[str],
) -> list[dict]:
    """generate_posts_multilang 결과를 enqueue 가능한 플랫 리스트로 변환.

    반환: [{"lang": "ja", "platform": "instagram", "topic": "...", "post": {...}}, ...]
    """
    items = []
    for lang, posts in multilang_posts.items():
        if lang == "_mode":
            continue
        for platform in platforms:
            post = posts.get(platform)
            if post and isinstance(post, dict):
                items.append({"lang": lang, "platform": platform, "post": post})
    return items
