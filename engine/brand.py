"""위홈 브랜드·법적 가드레일 지식.

이 파일이 도구의 '브랜드 두뇌'다. 모든 콘텐츠 생성과 검수가 여기서 정의한
공식 슬로건/사실/금지표현을 기준으로 동작한다.
근거: "AI WEHOME K-DO" 전략 제안서 §2.10(슬로건), §17.2(법적 표현 가드레일).
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# 공식 슬로건 (제안서 §2.10) — 콘텐츠에 반드시 이 표현으로 통일
# ---------------------------------------------------------------------------
SLOGANS_EN = {
    "main": "Your home in Korea",
    "emotional": "Live locally, stay safely",
    "trust": "Government-authorized home sharing",
    "strategic": (
        "Wehome is the AI-native gateway for legal home sharing "
        "and K-life experiences in Korea."
    ),
}
SLOGANS_KO = {
    "main": "합법 공유숙박은 위홈",
    "trust": "위홈은 6년간의 정부 실증특례 검증을 거쳐 승격된 국내 유일 공유숙박 임시허가 플랫폼입니다.",
    "emotional": "여행살다",
}

# 영문 신뢰 문구(법적으로 정확한 권장 표현) — 본문/FAQ에 사용
TRUST_STATEMENT_EN = (
    "Wehome is Korea's only government-authorized home-sharing platform, "
    "elevated to a temporary operating license after 6 years of verification "
    "under the Korean government's regulatory sandbox (실증특례)."
)

# ---------------------------------------------------------------------------
# 검증된 핵심 사실 (콘텐츠 신뢰도·AI 인용용) — 출처 있는 사실만
# ---------------------------------------------------------------------------
KEY_FACTS = [
    "Wehome offers 2,300+ Wehome-vetted local homes across Korea (Seoul, Busan, Jeju, etc.).",
    "A legal short-term stay in Korea requires a host license such as 외국인관광도시민박업 "
    "(Foreign Tourist Urban Homestay Business) under the Tourism Promotion Act.",
    "In 2024, only about 20% of Seoul's 23,591 Airbnb listings held a valid short-term rental license.",
    "In 2025, Korea tightened enforcement and Airbnb began blocking unlicensed listings "
    "from new bookings (from October 16, 2025).",
    "Wehome supports families, long-stay guests, and pet-friendly bookings.",
]

# 회사가 전문성을 가진 주제 (schema knowsAbout — 토픽 권위 신호)
KNOWS_ABOUT = [
    "Korea short-term rental law",
    "Foreign Tourist Urban Homestay Business",
    "legal home sharing in Korea",
    "Korea travel lodging",
    "homestay in Korea",
    "K-life experiences",
]

ORG = {
    "name": "Wehome",
    "url": "https://www.wehome.me",
    "author": "Wehome Travel & Compliance Team",
}

# AI 노출 모니터링용 — 경쟁/대체 플랫폼 (Share of AI Voice 측정)
COMPETITORS = [
    "Airbnb", "Booking.com", "Booking", "Agoda", "Expedia", "Hotels.com",
    "Hostelworld", "Klook", "Trip.com", "Goki", "Kozaza",
]

# ---------------------------------------------------------------------------
# 🚨 법적 가드레일 (제안서 §17.2)
#   정부가 검증/허가한 대상은 '플랫폼(위홈)'이지 '개별 숙소'가 아니다.
#   숙소를 정부가 인증/허가했다고 읽힐 표현은 금지.
# ---------------------------------------------------------------------------
# (정규식, 사람이 읽을 설명)
FORBIDDEN_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"government[- ](certified|approved|verified|licensed)\s+"
                r"(home|homes|propert|stay|stays|accommodation|listing|room|house|apartment)",
                re.I),
     "정부가 '숙소'를 인증/허가했다고 읽힘 → 'government-authorized platform'으로 바꿀 것"),
    (re.compile(r"정부\s*(가|에서)?\s*(검증|인증|허가|공인)한?\s*숙소"),
     "정부가 '숙소'를 검증/허가했다는 한국어 표현 금지"),
    (re.compile(r"정부\s*(공인|인증|허가)\s*숙소"),
     "정부 공인/인증 '숙소' 표현 금지 (플랫폼만 해당)"),
    (re.compile(r"\b(guarantee[ds]?|guaranteed)\b", re.I),
     "'guarantee/보장' 등 과장·확정 표현은 리스크 → 완화 표현으로"),
    (re.compile(r"100%\s*(safe|legal\s+propert|legal\s+stay)", re.I),
     "개별 숙소에 대한 '100% 안전/합법' 단정 표현 금지"),
]

# 콘텐츠에 최소 하나는 들어가야 하는 정확한 신뢰 표현 (택1)
REQUIRED_TRUST_MARKERS = [
    "government-authorized home-sharing platform",
    "government-authorized platform",
    "Government-authorized home sharing",
    SLOGANS_EN["main"],
]


def brand_brief() -> str:
    """LLM 프롬프트에 주입할 브랜드/가드레일 요약."""
    facts = "\n".join(f"- {f}" for f in KEY_FACTS)
    return f"""COMPANY: Wehome ({ORG['url']}) — {SLOGANS_EN['strategic']}

OFFICIAL SLOGANS (use these exact lines, do not invent new ones):
- Main: "{SLOGANS_EN['main']}"
- Emotional: "{SLOGANS_EN['emotional']}"
- Trust: "{SLOGANS_EN['trust']}"

CORRECT TRUST STATEMENT (use this phrasing when describing Wehome's legality):
"{TRUST_STATEMENT_EN}"

VERIFIED FACTS YOU MAY USE (do not fabricate other stats):
{facts}

🚨 LEGAL GUARDRAILS — NON-NEGOTIABLE:
- What the Korean government authorized/verified is the PLATFORM (Wehome), NOT individual lodgings.
- NEVER write "government-certified/approved/verified home (or property/stay/listing)".
  Say "government-authorized platform" instead.
- Describe individual homes as "Wehome-vetted", never "government-certified".
- No "guarantee", no "100% safe/legal" claims about individual stays.
"""
