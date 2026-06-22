"""한국 시즌·이벤트 캘린더 — 2주 전 자동 캠페인 트리거.

연간 반복 이벤트(공휴일·시즌)와 확정 일정(콘서트·축제)을 관리한다.
이벤트 D-14 에 due_campaigns() 가 해당 항목을 반환 → Discord 봇이 자동 캠페인 생성.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field

KST = datetime.timezone(datetime.timedelta(hours=9))


@dataclass
class KoreanEvent:
    name_ko: str
    name_en: str
    month: int
    day: int
    duration_days: int = 7
    lead_days: int = 14          # 캠페인 시작 시점 (이벤트 N일 전)
    topic_ko: str = ""           # generate_posts에 넘길 주제 (한국어)
    topic_en: str = ""           # 영어 주제
    topic_ja: str = ""           # 일본어 주제
    hashtags: list[str] = field(default_factory=list)
    year: int | None = None      # None = 매년 반복, 정수 = 특정 연도만


# ---------------------------------------------------------------------------
# 이벤트 데이터베이스 (연간 반복 + 주요 확정 일정)
# ---------------------------------------------------------------------------
_EVENTS: list[KoreanEvent] = [
    # ── 공휴일·명절 ──────────────────────────────────────────────────────
    KoreanEvent(
        name_ko="설날", name_en="Seollal (Korean Lunar New Year)",
        month=1, day=28, duration_days=3, year=2026,
        topic_ko="설날 한국 여행 — 위홈에서 특별한 명절 경험",
        topic_en="Korean Lunar New Year (Seollal) stay with Wehome",
        topic_ja="韓国の旧正月「ソルラル」でWehome滞在",
        hashtags=["#설날", "#Seollal", "#LunarNewYear", "#VisitKorea", "#위홈"],
    ),
    KoreanEvent(
        name_ko="추석", name_en="Chuseok (Korean Thanksgiving)",
        month=10, day=5, duration_days=3, year=2026,
        topic_ko="추석 황금 연휴 한국 여행 — 위홈 정부인증 숙소",
        topic_en="Chuseok Golden Holiday: Experience Korea with Wehome",
        topic_ja="韓国のお盆「チュソク」連休にWehomeで滞在",
        hashtags=["#추석", "#Chuseok", "#KoreaHoliday", "#위홈"],
    ),

    # ── 자연 시즌 ─────────────────────────────────────────────────────────
    KoreanEvent(
        name_ko="벚꽃 시즌", name_en="Cherry Blossom Season",
        month=3, day=28, duration_days=14,
        topic_ko="한국 벚꽃 시즌 — 위홈에서 꽃구경 여행 숙소 예약",
        topic_en="Korea Cherry Blossom Season: Book your Wehome stay now",
        topic_ja="韓国の桜シーズン到来！Wehomeで春旅を",
        hashtags=["#벚꽃", "#CherryBlossom", "#KoreaSakura", "#SpringKorea", "#위홈"],
    ),
    KoreanEvent(
        name_ko="단풍 시즌", name_en="Autumn Foliage Season",
        month=10, day=18, duration_days=21,
        topic_ko="한국 단풍 시즌 — 가을 여행 위홈 숙소 추천",
        topic_en="Korea Autumn Foliage Season: Stay with Wehome",
        topic_ja="韓国の紅葉シーズン！秋旅はWehomeで",
        hashtags=["#단풍", "#AutumnKorea", "#FallFoliage", "#KoreaTravel", "#위홈"],
    ),
    KoreanEvent(
        name_ko="여름 성수기", name_en="Korea Summer Peak Season",
        month=7, day=15, duration_days=45,
        topic_ko="여름 한국 여행 성수기 — 위홈 정부인증 숙소로 시원하게",
        topic_en="Korea Summer Travel Peak: Book your Wehome stay early",
        topic_ja="韓国夏の観光シーズン！Wehomeで早めの予約を",
        hashtags=["#한국여름여행", "#KoreaSummer", "#VisitKorea", "#위홈"],
    ),
    KoreanEvent(
        name_ko="스키 시즌", name_en="Korea Ski Season",
        month=12, day=20, duration_days=60,
        topic_ko="한국 스키 시즌 오픈 — 평창·용평 근처 위홈 숙소",
        topic_en="Korea Ski Season Opens: Stay near slopes with Wehome",
        topic_ja="韓国スキーシーズン開幕！Wehomeでゲレンデ旅",
        hashtags=["#한국스키", "#KoreaSkiing", "#PyeongChang", "#위홈"],
    ),

    # ── K-팝·문화 이벤트 ───────────────────────────────────────────────
    KoreanEvent(
        name_ko="서울 패션위크 (봄)", name_en="Seoul Fashion Week (Spring)",
        month=3, day=16, duration_days=7,
        topic_ko="서울 패션위크 — 위홈에서 트렌디한 서울 여행",
        topic_en="Seoul Fashion Week: Experience the trend with Wehome",
        topic_ja="ソウルファッションウィーク！Wehomeでトレンド旅",
        hashtags=["#서울패션위크", "#SFW", "#SeoulFashion", "#위홈"],
    ),
    KoreanEvent(
        name_ko="서울 패션위크 (가을)", name_en="Seoul Fashion Week (Fall)",
        month=10, day=12, duration_days=7,
        topic_ko="가을 서울 패션위크 — K-패션의 중심에서 위홈",
        topic_en="Seoul Fashion Week Fall: Stay in style with Wehome",
        topic_ja="秋のソウルファッションウィーク！Wehomeで",
        hashtags=["#서울패션위크", "#SFW", "#KFashion", "#위홈"],
    ),
    KoreanEvent(
        name_ko="부산국제영화제 (BIFF)", name_en="Busan International Film Festival",
        month=10, day=1, duration_days=10,
        topic_ko="부산국제영화제 BIFF — 위홈 부산 숙소로 영화제 여행",
        topic_en="BIFF Busan: Watch world cinema, stay with Wehome",
        topic_ja="釜山国際映画祭！WehomeでBIFF旅",
        hashtags=["#BIFF", "#부산국제영화제", "#BusanFilmFestival", "#위홈"],
    ),
    KoreanEvent(
        name_ko="서울 빛초롱 축제", name_en="Seoul Lantern Festival",
        month=11, day=1, duration_days=14,
        topic_ko="서울 빛초롱 축제 — 위홈에서 한국의 빛 축제 경험",
        topic_en="Seoul Lantern Festival: Magical nights with Wehome",
        topic_ja="ソウルランタンフェスティバル！Wehomeで夜の絶景を",
        hashtags=["#서울빛초롱", "#LanternFestival", "#SeoulNight", "#위홈"],
    ),
    KoreanEvent(
        name_ko="보령 머드 축제", name_en="Boryeong Mud Festival",
        month=7, day=11, duration_days=9,
        topic_ko="보령 머드 축제 — 한국 최대 여름 축제 위홈으로",
        topic_en="Boryeong Mud Festival: Korea's wildest summer fest with Wehome",
        topic_ja="泥のフェスティバル！韓国最大の夏祭りWehomeで",
        hashtags=["#보령머드축제", "#MudFestival", "#KoreaSummer", "#위홈"],
    ),
    KoreanEvent(
        name_ko="광복절 연휴", name_en="Korean Liberation Day Holiday",
        month=8, day=15, duration_days=3,
        topic_ko="광복절 연휴 한국 여행 — 위홈 정부인증 숙소",
        topic_en="Korea Liberation Day Long Weekend: Travel with Wehome",
        topic_ja="韓国光復節連休！Wehomeで歴史の地を旅する",
        hashtags=["#광복절", "#KoreaHoliday", "#위홈"],
    ),
]


# ---------------------------------------------------------------------------
# 조회 API
# ---------------------------------------------------------------------------

def all_events() -> list[KoreanEvent]:
    return list(_EVENTS)


def upcoming_events(days_ahead: int = 30) -> list[dict]:
    """오늘부터 N일 이내에 시작하는 이벤트 목록 반환."""
    today = datetime.datetime.now(KST).date()
    result = []
    for ev in _EVENTS:
        start = _resolve_date(ev, today.year)
        if start is None:
            continue
        days_until = (start - today).days
        if 0 <= days_until <= days_ahead:
            result.append(_to_dict(ev, start, days_until))
    return sorted(result, key=lambda x: x["start_date"])


def due_campaigns() -> list[dict]:
    """지금 캠페인을 시작해야 하는 이벤트 (D-lead_days ± 1) 반환."""
    today = datetime.datetime.now(KST).date()
    result = []
    for ev in _EVENTS:
        start = _resolve_date(ev, today.year)
        if start is None:
            continue
        days_until = (start - today).days
        # lead_days 당일(±0)에만 트리거 (중복 방지)
        if days_until == ev.lead_days:
            result.append(_to_dict(ev, start, days_until))
    return result


def _resolve_date(ev: KoreanEvent, current_year: int) -> datetime.date | None:
    """이벤트의 올해(또는 지정 연도) 시작일 반환. 이미 지난 날짜는 내년으로."""
    today = datetime.datetime.now(KST).date()
    year = ev.year if ev.year else current_year
    try:
        start = datetime.date(year, ev.month, ev.day)
    except ValueError:
        return None
    # 연간 반복 이벤트: 이미 올해 지났으면 내년으로
    if ev.year is None and start < today:
        try:
            start = datetime.date(current_year + 1, ev.month, ev.day)
        except ValueError:
            return None
    return start


def _to_dict(ev: KoreanEvent, start: datetime.date, days_until: int) -> dict:
    return {
        "name_ko": ev.name_ko,
        "name_en": ev.name_en,
        "start_date": start.isoformat(),
        "duration_days": ev.duration_days,
        "days_until": days_until,
        "lead_days": ev.lead_days,
        "topic_ko": ev.topic_ko or ev.name_ko,
        "topic_en": ev.topic_en or ev.name_en,
        "topic_ja": ev.topic_ja or ev.name_en,
        "hashtags": ev.hashtags,
    }
