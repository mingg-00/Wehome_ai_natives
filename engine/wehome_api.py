"""위홈 데이터 소스 어댑터.

- WEHOME_API_BASE/KEY가 설정되면 실제 위홈 예약 API를 호출한다.
- 미설정(또는 호출 실패)이면 data/sample_stays.json 으로 폴백한다.

→ 자격증명만 .env에 넣으면 도구·MCP·Open API가 즉시 실데이터로 동작한다.
   (실제 API 응답 필드명이 다르면 _map_stay() 한 곳만 고치면 됨.)
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from .config import DATA_DIR, settings

# 내부 표준 스키마 (도구가 기대하는 필드)
_INTERNAL_FIELDS = ("id", "name", "city", "area", "type", "max_guests",
                    "price_per_night_krw", "pet_friendly", "long_stay",
                    "amenities", "vibe", "near", "good_for")


def _sample() -> list[dict]:
    return json.loads((DATA_DIR / "sample_stays.json").read_text(encoding="utf-8"))


def _map_stay(raw: dict) -> dict:
    """실제 위홈 API 응답 → 내부 표준 스키마 매핑.
    필드명이 다르면 여기만 조정하면 된다."""
    return {
        "id": raw.get("id") or raw.get("listing_id"),
        "name": raw.get("name") or raw.get("title"),
        "city": raw.get("city", ""),
        "area": raw.get("area") or raw.get("district", ""),
        "type": raw.get("type", "Whole home"),
        "max_guests": raw.get("max_guests") or raw.get("capacity", 0),
        "price_per_night_krw": raw.get("price_per_night_krw") or raw.get("price", 0),
        "pet_friendly": bool(raw.get("pet_friendly", False)),
        "long_stay": bool(raw.get("long_stay", False)),
        "amenities": raw.get("amenities", []),
        "vibe": raw.get("vibe", ""),
        "near": raw.get("near") or raw.get("nearest_station", ""),
        "good_for": raw.get("good_for", []),
    }


def get_stays() -> list[dict]:
    """숙소 목록을 반환 (실제 API 우선, 실패 시 샘플 폴백)."""
    if not settings.wehome_api_enabled:
        return _sample()
    try:
        url = settings.wehome_api_base.rstrip("/") + "/stays"
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {settings.wehome_api_key}",
            "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        raw_list = data.get("stays", data) if isinstance(data, dict) else data
        return [_map_stay(r) for r in raw_list]
    except Exception as e:  # 실패 시 안전하게 샘플로 폴백
        print(f"⚠️ 위홈 API 호출 실패({e}) → 샘플 데이터 사용")
        return _sample()


def source_label() -> str:
    return "live-api" if settings.wehome_api_enabled else "sample"
