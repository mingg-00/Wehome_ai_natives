"""여행 트렌드 감지 — Google News RSS 기반 키워드 추출.

Google Trends API가 폐쇄됨에 따라 Google News RSS에서 한국 여행·숙소
관련 최신 뉴스 헤드라인을 수집하고, 위홈과 연관된 키워드를 추출한다.
인증 불필요, 하루 1회 실행.
"""
from __future__ import annotations

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# 뉴스 검색 쿼리 목록
_NEWS_QUERIES = ["한국 여행 숙소", "한국 관광 여행", "K-pop 여행 한국"]

# 위홈 연관 지역
_WEHOME_LOCATIONS = [
    "부산", "제주", "서울", "강남", "홍대", "이태원", "명동",
    "해운대", "광안리", "전주", "경주", "강릉", "속초", "여수",
    "가평", "평창", "인천", "수원", "성수", "마포", "잠실",
]

# 여행 관련 긍정 키워드
_TRAVEL_POSITIVE = [
    "여행", "숙소", "관광", "인기", "핫플", "트렌드", "추천",
    "성수기", "할인", "축제", "K-pop", "한류",
]

# 제외 키워드 (부정적 뉴스)
_EXCLUDE = ["사고", "사망", "범죄", "화재", "재난", "논란", "사기", "피해"]

_NEWS_RSS = "https://news.google.com/rss/search?q={query}&hl=ko&gl=KR&ceid=KR:ko"


def _fetch_news_titles(query: str, count: int = 30) -> list[str]:
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


def _extract_keywords(titles: list[str]) -> list[str]:
    """헤드라인에서 지역·여행 키워드 빈도 기반 추출."""
    text = " ".join(titles)
    found: Counter = Counter()

    for loc in _WEHOME_LOCATIONS:
        cnt = text.count(loc)
        if cnt >= 2:
            found[loc] += cnt * 2  # 지역명 가중치 2배

    for kw in _TRAVEL_POSITIVE:
        cnt = text.count(kw)
        if cnt >= 2:
            found[kw] += cnt

    return [kw for kw, _ in found.most_common(10)]


def fetch_trending(count: int = 10) -> list[str]:
    """뉴스 헤드라인 기반 여행 트렌드 키워드 반환."""
    all_titles: list[str] = []
    for query in _NEWS_QUERIES:
        all_titles.extend(_fetch_news_titles(query, count=30))

    if not all_titles:
        return []

    return _extract_keywords(all_titles)[:count]


def filter_wehome_relevant(keywords: list[str]) -> list[dict]:
    """키워드 중 위홈 연관 항목 → 캠페인 주제 생성."""
    results = []
    for keyword in keywords:
        if any(ex in keyword for ex in _EXCLUDE):
            continue

        is_location = keyword in _WEHOME_LOCATIONS
        is_travel = keyword in _TRAVEL_POSITIVE

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
