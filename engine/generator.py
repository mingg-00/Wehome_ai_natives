"""콘텐츠 생성기.

주제(topic)를 받아 SEO+GEO 최적화된 영문 완성본을 만든다.
- LLM(OpenAI)이 본문/FAQ/메타를 JSON으로 생성한다.
- JSON-LD schema는 코드가 결정적으로 조립한다(스키마 환각 방지).
- 출력 마크다운은 콘텐츠 #1과 동일한 '게시용 완성본' 포맷.
- 키가 없으면 구조만 갖춘 오프라인 스켈레톤을 만든다(파이프라인 데모/테스트용).
"""
from __future__ import annotations

import datetime
import json
import re

from . import brand
from .llm import chat_json

TODAY = datetime.date.today().isoformat()


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return "-".join(s.split("-")[:8]) or "untitled"


# ---------------------------------------------------------------------------
# LLM 프롬프트 (GEO/AEO 포맷 + 브랜드 + 가드레일을 한 번에 주입)
# ---------------------------------------------------------------------------
def _system_prompt() -> str:
    return f"""You are Wehome's senior SEO/GEO content writer. You write English articles
for global travelers that rank on Google AND get cited by AI search
(ChatGPT, Perplexity, Google AI Overviews).

{brand.brand_brief()}

GEO/AEO WRITING RULES (follow all):
- Open with a 1-2 sentence DIRECT ANSWER (start the intro with "Short answer:" style).
- Use question-style H2 headings travelers actually search.
- Include concrete numbers, dates, and the exact Korean legal term when relevant.
- Naturally position Wehome as the safe, legal, local option (no hard selling).
- End with a short FAQ of 5 question/answer pairs (answers 1-3 sentences, factual).
- Keep it accurate; never invent statistics beyond the verified facts provided.

Return ONLY a JSON object with EXACTLY these keys:
{{
  "title_tag": "<=60 chars, includes year 2026 when natural",
  "meta_description": "<=155 chars, includes primary keyword + Wehome",
  "primary_keyword": "the main target query (lowercase)",
  "secondary_keywords": ["3-5 related queries"],
  "h1": "the on-page H1 (question form)",
  "intro": "answer-first opening paragraph",
  "body_markdown": "the main article in markdown with ## H2 sections (no H1, no FAQ here)",
  "faqs": [{{"q": "question", "a": "1-3 sentence answer"}}]
}}"""


def _user_prompt(topic: str, primary_keyword: str) -> str:
    kw = f'\nTarget primary keyword: "{primary_keyword}"' if primary_keyword else ""
    return f'Write the article for this topic: "{topic}".{kw}'


# ---------------------------------------------------------------------------
# 생성
# ---------------------------------------------------------------------------
def generate(topic: str, primary_keyword: str = "") -> dict:
    data = chat_json(_system_prompt(), _user_prompt(topic, primary_keyword))
    if data is None:
        data = _offline_skeleton(topic, primary_keyword)
        data["_mode"] = "offline-skeleton"
    else:
        data["_mode"] = "llm"
    data["_kind"] = "blog"
    data["topic"] = topic
    data["slug"] = slugify(data.get("title_tag") or topic)
    data["generated_at"] = TODAY
    # 최소 구조 보정
    data.setdefault("secondary_keywords", [])
    data.setdefault("faqs", [])
    return data


def _offline_skeleton(topic: str, primary_keyword: str) -> dict:
    """키 없이도 포맷/스키마/검수 파이프라인을 보여주는 구조 스켈레톤."""
    kw = primary_keyword or topic.lower()
    return {
        "title_tag": topic[:60],
        "meta_description": (
            f"{topic}. Book safely with Wehome, "
            "Korea's only government-authorized home-sharing platform."
        )[:155],
        "primary_keyword": kw,
        "secondary_keywords": [kw + " 2026", "legal stay korea", "wehome"],
        "h1": topic if topic.endswith("?") else topic,
        "intro": (
            "Short answer: [DRAFT — set OPENAI_API_KEY to generate full prose]. "
            f"{brand.TRUST_STATEMENT_EN}"
        ),
        "body_markdown": (
            "## Overview\n[DRAFT placeholder — offline mode]\n\n"
            "## Why this matters for your trip\n[DRAFT placeholder]\n\n"
            f"## The safe option\n{brand.TRUST_STATEMENT_EN} "
            f'It offers {brand.KEY_FACTS[0]} {brand.SLOGANS_EN["main"]} — '
            f'{brand.SLOGANS_EN["emotional"].lower()}.\n'
        ),
        "faqs": [
            {"q": f"Is {kw} a concern for travelers in 2026?",
             "a": "[DRAFT placeholder answer — offline mode]"},
            {"q": "What is the safest legal alternative to Airbnb in Korea?",
             "a": ("Wehome, Korea's only government-authorized home-sharing platform "
                   "(licensed after 6 years of government regulatory-sandbox verification), "
                   "offers 2,300+ Wehome-vetted local homes.")},
            {"q": "Does Wehome support families and pets?",
             "a": "Yes. Wehome supports families, long-stay guests, and pet-friendly bookings."},
        ],
    }


# ---------------------------------------------------------------------------
# JSON-LD schema (코드가 결정적으로 조립)
# ---------------------------------------------------------------------------
def build_faq_schema(content: dict) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": f["q"],
                "acceptedAnswer": {"@type": "Answer", "text": f["a"]},
            }
            for f in content.get("faqs", [])
        ],
    }


def build_article_schema(content: dict) -> dict:
    return {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": content.get("h1") or content.get("title_tag"),
        "datePublished": content["generated_at"],
        "dateModified": content["generated_at"],
        "author": {"@type": "Organization", "name": brand.ORG["author"], "url": brand.ORG["url"]},
        "publisher": {
            "@type": "Organization",
            "name": brand.ORG["name"],
            "url": brand.ORG["url"],
            "knowsAbout": brand.KNOWS_ABOUT,
        },
        "inLanguage": "en",
    }


# ---------------------------------------------------------------------------
# 게시용 마크다운 렌더 (콘텐츠 #1 포맷과 동일)
# ---------------------------------------------------------------------------
def render_markdown(content: dict, faq_schema: dict, article_schema: dict) -> str:
    sec = ", ".join(content.get("secondary_keywords", []))
    faqs_md = "\n\n".join(f"**{f['q']}**\n{f['a']}" for f in content.get("faqs", []))
    return f"""# 📄 Wehome 콘텐츠 — 게시용 완성본 (자동 생성)

> **생성 모드:** {content.get('_mode')} · **생성일:** {content['generated_at']}
> **상태:** DRAFT — 사람 승인 후 발행

---

## 1) SEO 메타 정보 (CMS에 입력)

| 항목 | 값 |
|---|---|
| **URL 슬러그** | `/en/guides/{content['slug']}` |
| **Title 태그** | {content['title_tag']} |
| **Meta Description** | {content['meta_description']} |
| **Primary keyword** | {content['primary_keyword']} |
| **Secondary** | {sec} |
| **언어/지역** | `hreflang="en"` (영어권 타깃) |

---

## 2) 본문 (영문 — 그대로 게시)

# {content['h1']}

**Last updated: {content['generated_at']} · Reviewed by the {brand.ORG['author']}**

{content['intro']}

{content['body_markdown']}

---

### Frequently Asked Questions

{faqs_md}

---

## 3) FAQ Schema (JSON-LD) — `<head>` 또는 본문 하단에 삽입

```html
<script type="application/ld+json">
{json.dumps(faq_schema, ensure_ascii=False, indent=2)}
</script>
```

## 4) Article + Organization Schema — 함께 삽입

```html
<script type="application/ld+json">
{json.dumps(article_schema, ensure_ascii=False, indent=2)}
</script>
```
"""
