"""신규 숙소 자동 감지 — wehome.me 크롤링 → 맞춤 포스팅 생성.

wehome.me/ko/s 페이지를 크롤링해 숙소 ID 목록을 추출하고,
이전 스냅샷과 비교해 신규 숙소를 감지한다.
신규 숙소 발견 시 상세 페이지를 크롤링해 맞춤 포스팅 주제를 생성한다.
"""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import OUTPUT_DIR

_SNAPSHOT_FILE = OUTPUT_DIR / "known_properties.json"
_LIST_URL = "https://www.wehome.me/ko/s"
_ROOM_URL = "https://www.wehome.me/ko/rooms/{room_id}"
_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# 지역명 매핑 (URL/텍스트에서 추출)
_REGION_KEYWORDS = {
    # 서울 세부 지역
    "강남": "Gangnam", "홍대": "Hongdae", "이태원": "Itaewon",
    "명동": "Myeongdong", "신촌": "Sinchon", "성수": "Seongsu",
    "마포": "Mapo", "종로": "Jongno", "잠실": "Jamsil",
    "신림": "Sillim", "강동": "Gangdong", "송파": "Songpa",
    "여의도": "Yeouido", "건대": "Konkuk", "합정": "Hapjeong",
    # 부산 세부 지역
    "광안리": "Gwangalli", "해운대": "Haeundae", "서면": "Seomyeon",
    "남포": "Nampo", "부산": "Busan",
    # 광역시·도시
    "서울": "Seoul", "제주": "Jeju", "인천": "Incheon",
    "수원": "Suwon", "대구": "Daegu", "광주": "Gwangju",
    "전주": "Jeonju", "경주": "Gyeongju", "강릉": "Gangneung",
    "속초": "Sokcho", "여수": "Yeosu", "평창": "Pyeongchang",
    "가평": "Gapyeong", "양평": "Yangpyeong",
}


@dataclass
class PropertySummary:
    room_id: str
    title: str
    region_ko: str
    region_en: str
    image_url: str
    room_url: str
    topic_ko: str
    topic_en: str
    topic_ja: str
    hashtags: list[str]


def _fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", errors="replace")


def _extract_room_ids(html: str) -> set[str]:
    return set(re.findall(r'/rooms/(\d+)', html))


def _load_snapshot() -> set[str]:
    if _SNAPSHOT_FILE.exists():
        return set(json.loads(_SNAPSHOT_FILE.read_text(encoding="utf-8")))
    return set()


def _save_snapshot(ids: set[str]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _SNAPSHOT_FILE.write_text(
        json.dumps(sorted(ids), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _detect_region(text: str) -> tuple[str, str]:
    # 긴 키워드 우선 매칭 (강남 > 서울, 광안리 > 부산)
    for ko, en in sorted(_REGION_KEYWORDS.items(), key=lambda x: -len(x[0])):
        if ko in text:
            return ko, en
    return "한국", "Korea"


def _fetch_property_detail(room_id: str) -> PropertySummary | None:
    url = _ROOM_URL.format(room_id=room_id)
    try:
        html = _fetch_html(url)
    except Exception as e:
        print(f"[PropertyMonitor] 숙소 상세 크롤링 실패 {room_id}: {e}")
        return None

    # 제목 추출 (og:title 또는 title 태그)
    title_match = (
        re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\'](.*?)["\']', html)
        or re.search(r'<title>(.*?)</title>', html)
    )
    title = title_match.group(1).strip() if title_match else f"위홈 숙소 #{room_id}"
    # "숙소 예약 | 위홈 (한국)" 등 불필요한 suffix 제거
    title = re.sub(r'\s*숙소\s*예약.*$', '', title).strip()
    title = re.sub(r'\s*[|｜–—-]\s*(위홈|Wehome).*$', '', title, flags=re.IGNORECASE).strip()

    # 대표 이미지 추출
    img_match = re.search(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](.*?)["\']', html
    )
    image_url = img_match.group(1).strip() if img_match else ""

    # 지역 감지 — 제목 우선, 없으면 HTML 앞부분에서 검색
    region_ko, region_en = _detect_region(title + " " + html[:3000])

    # 숙소 유형 감지
    type_ko = "숙소"
    for kw in ["한옥", "빌라", "펜션", "게스트하우스", "아파트", "원룸"]:
        if kw in html[:3000]:
            type_ko = kw
            break

    # 포스팅 주제 생성
    topic_ko = f"[신규 등록] {title} — {region_ko} 위홈 정부인증 {type_ko}"
    topic_en = f"[New Listing] {title} — Government-authorized {type_ko} in {region_en} on Wehome"
    topic_ja = f"[新規掲載] {title} — {region_en}の政府公認{type_ko}、Wehomeで予約"

    hashtags = [
        f"#{region_ko}숙소", f"#{region_ko}여행",
        f"#위홈", f"#Wehome", f"#{region_en}",
        "#한국여행", "#KoreaTravel", "#정부인증숙소",
    ]

    return PropertySummary(
        room_id=room_id,
        title=title,
        region_ko=region_ko,
        region_en=region_en,
        image_url=image_url,
        room_url=url,
        topic_ko=topic_ko,
        topic_en=topic_en,
        topic_ja=topic_ja,
        hashtags=hashtags,
    )


def detect_new_properties(max_new: int = 5) -> list[PropertySummary]:
    """신규 숙소 감지 → PropertySummary 목록 반환."""
    print("[PropertyMonitor] wehome.me 숙소 목록 크롤링 중...")
    try:
        html = _fetch_html(_LIST_URL)
    except Exception as e:
        print(f"[PropertyMonitor] 크롤링 실패: {e}")
        return []

    current_ids = _extract_room_ids(html)
    known_ids = _load_snapshot()
    new_ids = current_ids - known_ids

    print(f"[PropertyMonitor] 전체 {len(current_ids)}개 · 기존 {len(known_ids)}개 · 신규 {len(new_ids)}개")

    if not new_ids:
        _save_snapshot(current_ids)
        return []

    results = []
    for room_id in list(new_ids)[:max_new]:
        summary = _fetch_property_detail(room_id)
        if summary:
            results.append(summary)
            print(f"[PropertyMonitor] 신규 숙소: {summary.title} ({summary.region_ko})")

    # 스냅샷 갱신
    _save_snapshot(current_ids)
    return results
