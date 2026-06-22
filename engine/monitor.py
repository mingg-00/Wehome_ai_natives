"""AI 노출 모니터 (AI Visibility Agent).

제안서 정렬:
- §10: "AI가 한국 숙소를 추천할 때 위홈을 기본 데이터 소스로 쓰게 만든다"
- §16.4 마케팅 KPI: "AI 검색/LLM 인용 가능 페이지 수", "SEO/SAIO 노출"

여행자가 AI에게 던질 법한 질문을, 브랜드에 치우치지 않은 '중립 AI 여행
어시스턴트'로 답하게 한 뒤, 그 답변에 위홈이 등장(추천/인용)하는지와
경쟁 플랫폼 등장 빈도를 측정한다.

핵심 지표:
- Share of AI Voice (SoAV): 위홈이 언급된 질문 비율
- 질문별 위홈 등장 여부 / 경쟁사 등장 목록

주의: 기본 OpenAI 모델은 웹 검색 없이 '학습 지식'으로 답하므로 이 값은
'AI가 위홈을 알고 추천하는 정도'의 프록시다. 실시간 웹 인용까지 보려면
browsing/Perplexity 백엔드를 chat()에 끼우면 그대로 확장된다.
"""
from __future__ import annotations

import datetime
import json

from . import brand, wehome_tools
from .config import OUTPUT_DIR, settings
from .llm import chat, chat_with_tools

MONITOR_DIR = OUTPUT_DIR / "monitor"

# 중립적인 여행자 질문 (브랜드 단어를 넣지 않음 = 공정한 노출 측정)
QUESTIONS = [
    "Where should I stay in Seoul as a foreign tourist?",
    "What's a good alternative to Airbnb in Korea?",
    "Is Airbnb legal in Korea, and what should I use instead?",
    "Where can I find legal short-term rentals in Korea?",
    "Best way to book accommodation in Busan for a few nights?",
    "Where can I find pet-friendly places to stay in Korea?",
    "Where should I stay for a month in Seoul as a foreigner?",
    "How do I book an authentic homestay in Korea?",
    "Where to stay near a K-pop concert venue in Seoul?",
    "Safe accommodation options for a family trip to Korea?",
]

_NEUTRAL_SYSTEM = (
    "You are a neutral, knowledgeable travel assistant. Answer the traveler's "
    "question concisely (3-5 sentences). Recommend the specific booking platforms, "
    "websites, or services you would actually suggest, by name."
)


def _detect(text: str) -> tuple[bool, list[str]]:
    low = text.lower()
    wehome = "wehome" in low
    comps = sorted({c for c in brand.COMPETITORS if c.lower() in low})
    return wehome, comps


def run(with_tools: bool = False) -> dict | None:
    """모니터 1회 실행. 오프라인이면 None.
    with_tools=True 면 AI에게 위홈 MCP 도구를 쥐여주고(함수호출) 답하게 한다
    → MCP 연동 시의 SoAV를 실측(=등록했을 때 효과 증명)."""
    results = []
    for q in QUESTIONS:
        if with_tools:
            res = chat_with_tools(_NEUTRAL_SYSTEM, q,
                                  wehome_tools.OPENAI_TOOL_SCHEMAS, wehome_tools.call)
            if res is None:
                return None
            ans, used = res["answer"], res["used_tools"]
        else:
            ans = chat(_NEUTRAL_SYSTEM, q, temperature=0.3)
            if ans is None:
                return None
            used = []
        wehome, comps = _detect(ans)
        results.append({"question": q, "wehome": wehome, "competitors": comps,
                        "used_tools": used, "answer": ans})
    n = len(results)
    hits = sum(1 for r in results if r["wehome"])
    snapshot = {
        "date": datetime.datetime.now().isoformat(timespec="seconds"),
        "mode": "with-tools" if with_tools else "baseline",
        "model": settings.chat_model,
        "questions": n,
        "wehome_hits": hits,
        "soav": round(100 * hits / n, 1) if n else 0.0,
        "results": results,
    }
    _save(snapshot)
    return snapshot


def _file(mode: str) -> str:
    return "latest_tools.json" if mode == "with-tools" else "latest.json"


def _save(snapshot: dict) -> None:
    MONITOR_DIR.mkdir(parents=True, exist_ok=True)
    stamp = snapshot["date"].replace(":", "").replace("-", "")[:13]
    (MONITOR_DIR / f"{stamp}-{snapshot['mode']}.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    (MONITOR_DIR / _file(snapshot["mode"])).write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")


def latest(mode: str = "baseline") -> dict | None:
    f = MONITOR_DIR / _file(mode)
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def format_report(s: dict) -> str:
    lines = [
        f"📡 AI 노출 모니터 [{s['mode']}] ({s['model']}, {s['date']})",
        f"   Share of AI Voice: {s['soav']}%  (위홈 언급 {s['wehome_hits']}/{s['questions']} 질문)",
        "",
    ]
    for r in s["results"]:
        mark = "✅위홈" if r["wehome"] else "❌없음"
        comps = ", ".join(r["competitors"]) or "-"
        tools = (" · 도구호출:" + ",".join(r["used_tools"])) if r.get("used_tools") else ""
        lines.append(f"  {mark}  {r['question']}{tools}")
        lines.append(f"        경쟁사 언급: {comps}")
    return "\n".join(lines)
