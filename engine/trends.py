"""여행 트렌드 감지 — Google News RSS + LLM 기반 키워드 추출.

Google Trends API가 폐쇄됨에 따라 Google News RSS에서 한국 여행·숙소
관련 최신 뉴스 헤드라인을 수집하고, LLM이 실제 트렌딩 토픽을 추출한다.
인증 불필요, 하루 1회 실행.
"""
from __future__ import annotations

import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from . import llm as _llm

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# 검색 쿼리 — 광범위하게 수집 후 LLM이 필터링
_NEWS_QUERIES = ["한국 숙소 예약", "제주 여행", "K-pop 관광 한국"]

# 결과에서 제외할 너무 일반적인 단어 (검색어 메아리 방지)
_TOO_GENERIC = {"여행", "관광", "숙소", "한국", "Korea", "여행자", "관광객"}

# 위홈 연관 지역 (지역명 감지용)
_WEHOME_LOCATIONS = [
    "부산", "제주", "서울", "강남", "홍대", "이태원", "명동",
    "해운대", "광안리", "전주", "경주", "강릉", "속초", "여수",
    "가평", "평창", "인천", "성수", "마포", "잠실", "춘천", "통영",
]

# 부정 뉴스 제외
_EXCLUDE = ["사고", "사망", "범죄", "화재", "재난", "논란", "사기", "피해"]

_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"

_TREND_EXTRACT_PROMPT = """다음은 한국 여행·숙소 관련 최신 뉴스 헤드라인 목록입니다.

{headlines}

위 헤드라인에서 지금 실제로 뜨고 있는 여행 트렌드 키워드를 최대 5개 추출하세요.

조건:
- "여행", "관광", "숙소", "한국" 같은 너무 일반적인 단어는 제외
- 한국 내 지역명, 이벤트, 테마, 특정 여행 스타일을 우선
- 해외 지명(멕시코, 유럽 도시 등 한국과 무관한 곳)은 절대 포함하지 말 것
- 위홈(한국 공유숙박 플랫폼) 콘텐츠와 연결 가능한 것만
- 부정적인 뉴스 키워드 제외

JSON으로만 응답: {{"keywords": ["키워드1", "키워드2", ...]}}"""


def _fetch_news_titles(query: str, count: int = 20) -> list[str]:
    url = _NEWS_RSS.format(query=urllib.parse.quote(query))
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            xml_text = r.read().decode("utf-8")
        root = ET.fromstring(xml_text)
        return [el.text for el in root.findall(".//item/title") if el.text][:count]
    except Exception as e:
        print(f"[Trends] 뉴스 수집 실패 ({query}): {e}")
        return []


def _extract_keywords_llm(titles: list[str]) -> list[str]:
    """LLM으로 헤드라인에서 실제 트렌딩 키워드 추출."""
    if not titles:
        return []
    headlines_text = "\n".join(f"- {t}" for t in titles[:40])
    prompt = _TREND_EXTRACT_PROMPT.format(headlines=headlines_text)
    data = _llm.chat_json("당신은 여행 트렌드 분석 전문가입니다.", prompt)
    if data and "keywords" in data:
        keywords = data["keywords"]
        # 너무 일반적인 단어 및 부정 키워드 필터링
        return [
            kw for kw in keywords
            if kw not in _TOO_GENERIC
            and not any(ex in kw for ex in _EXCLUDE)
        ]
    return []


def fetch_trending(count: int = 10) -> list[str]:
    """뉴스 헤드라인 기반 여행 트렌드 키워드 반환."""
    all_titles: list[str] = []
    for query in _NEWS_QUERIES:
        all_titles.extend(_fetch_news_titles(query))

    if not all_titles:
        return []

    keywords = _extract_keywords_llm(all_titles)
    print(f"[Trends] 추출된 트렌드 키워드: {keywords}")
    return keywords[:count]


def filter_wehome_relevant(keywords: list[str]) -> list[dict]:
    """키워드 중 위홈 연관 항목 → 캠페인 주제 생성."""
    results = []
    for keyword in keywords:
        if any(ex in keyword for ex in _EXCLUDE):
            continue

        is_location = keyword in _WEHOME_LOCATIONS or any(loc in keyword for loc in _WEHOME_LOCATIONS)

        if is_location:
            topic_ko = f"지금 핫한 {keyword} 여행 — 위홈 정부인증 숙소로 완벽한 여행"
            topic_en = f"Trending: {keyword} Travel — Book verified Wehome stays now"
            topic_ja = f"今話題の{keyword}旅行 — Wehomeで政府公認の宿を予約"
        else:
            topic_ko = f"{keyword} 트렌드 — 위홈 정부인증 한국 숙소"
            topic_en = f"Trending: {keyword} — Stay legally in Korea with Wehome"
            topic_ja = f"トレンド: {keyword} — Wehomeで韓国の公認宿泊施設へ"

        results.append({
            "keyword": keyword,
            "is_location": is_location,
            "topic_ko": topic_ko,
            "topic_en": topic_en,
            "topic_ja": topic_ja,
        })

    return results


def get_campaign_topics(max_topics: int = 3) -> list[dict]:
    """트렌드 감지 → 위홈 연관 캠페인 주제 반환."""
    keywords = fetch_trending()
    if not keywords:
        return []
    relevant = filter_wehome_relevant(keywords)
    print(f"[Trends] 위홈 연관 트렌드 {len(relevant)}개 감지")
    return relevant[:max_topics]
