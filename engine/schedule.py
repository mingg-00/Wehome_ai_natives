"""플랫폼별 골든타임 및 다음 예약 시각 계산.

골든타임 = SNS별 평균 참여율이 높은 시간대 (KST 기준).
실제 위홈 계정 인사이트 데이터가 쌓이면 GOLDEN_HOURS를 교체 권장.
"""
from __future__ import annotations

import datetime

# KST 기준 골든타임 (시 단위)
GOLDEN_HOURS: dict[str, list[int]] = {
    "instagram": [11, 19],   # 오전 11시, 저녁 7시
    "threads":   [12, 20],   # 점심 12시, 저녁 8시
    "facebook":  [13, 20],   # 오후 1시, 저녁 8시
    "x":         [9, 18],    # 오전 9시, 오후 6시
    "pinterest": [20, 21],   # 저녁 8~9시 (저장형 콘텐츠)
    "youtube":   [15, 20],   # 오후 3시, 저녁 8시
}

KST = datetime.timezone(datetime.timedelta(hours=9))
_FALLBACK = [12, 20]


def next_golden_time(platform: str, after: datetime.datetime | None = None) -> str:
    """platform의 다음 골든타임 ISO 문자열 반환 (KST)."""
    now = (after or datetime.datetime.now(KST)).astimezone(KST)
    hours = GOLDEN_HOURS.get(platform, _FALLBACK)

    for day_offset in range(3):
        d = now.date() + datetime.timedelta(days=day_offset)
        for h in sorted(hours):
            t = datetime.datetime(d.year, d.month, d.day, h, 0, tzinfo=KST)
            if t > now:
                return t.isoformat(timespec="seconds")

    # 3일 내 슬롯 없으면(이론상 불가) 내일 첫 슬롯
    d = now.date() + datetime.timedelta(days=1)
    return datetime.datetime(d.year, d.month, d.day, min(hours), 0, tzinfo=KST).isoformat(timespec="seconds")


def golden_hours_label(platform: str) -> str:
    """골든타임 표시 문자열 (예: '11시·19시')."""
    hours = GOLDEN_HOURS.get(platform, _FALLBACK)
    return "·".join(f"{h}시" for h in hours)


def is_due(scheduled_at: str) -> bool:
    """scheduled_at(ISO 문자열)이 현재 시각 이전이면 True."""
    try:
        t = datetime.datetime.fromisoformat(scheduled_at)
        now = datetime.datetime.now(KST)
        if t.tzinfo is None:
            t = t.replace(tzinfo=KST)
        return t <= now
    except Exception:
        return True
