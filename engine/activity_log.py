"""자동화 활동 로그 — 이벤트 기록/조회 (JSONL append-only).

기록 대상:
  post     — SNS 게시 완료
  generate — 콘텐츠 AI 생성
  trend    — 트렌드 감지
  property — 신규 숙소 감지
  campaign — 시즌 캠페인 트리거
"""
from __future__ import annotations

import json
import datetime

from .config import OUTPUT_DIR

_LOG_FILE = OUTPUT_DIR / "activity_log.jsonl"
_KST = datetime.timezone(datetime.timedelta(hours=9))


def append(type_: str, msg: str, platform: str | None = None, detail: str = "") -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.datetime.now(_KST).isoformat(timespec="seconds"),
        "type": type_,
        "msg": msg,
        "platform": platform,
        "detail": detail,
    }
    with open(_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def recent(n: int = 40) -> list[dict]:
    """최근 n개 이벤트 (최신순)."""
    if not _LOG_FILE.exists():
        return []
    lines = _LOG_FILE.read_text(encoding="utf-8").strip().splitlines()
    entries: list[dict] = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except Exception:
            pass
    return list(reversed(entries[-n:]))
