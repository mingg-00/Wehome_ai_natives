"""자동 검수(Governance).

생성된 콘텐츠가 법적 가드레일(제안서 §17.2)과 GEO 포맷 기준을 지켰는지
자동 점검한다. FAIL이 하나라도 있으면 사람 승인 단계로 못 넘어간다.
"""
from __future__ import annotations

from . import brand


def review(content: dict, markdown: str) -> dict:
    """검수 리포트 반환: {status, fails, warns, passes}.
    포맷(content['_kind'])에 따라 적용 체크가 달라진다.
    - 공통(모든 포맷): 법적 금지표현·Wehome 언급 → FAIL
    - 블로그 전용: FAQ 3개·answer-first·메타 길이
    - 신뢰표현: 블로그는 FAIL, 짧은 포맷(reddit/shortform/pinterest)은 WARN
    """
    kind = content.get("_kind", "blog")
    fails: list[str] = []
    warns: list[str] = []
    passes: list[str] = []

    # 렌더된 전체 텍스트를 스캔 대상으로 (포맷 무관하게 견고)
    text = markdown

    # 1) 🚨 법적 금지표현 (모든 포맷 FAIL)
    hit_forbidden = False
    for pat, why in brand.FORBIDDEN_PATTERNS:
        m = pat.search(text)
        if m:
            fails.append(f"금지표현 '{m.group(0)}' → {why}")
            hit_forbidden = True
    if not hit_forbidden:
        passes.append("법적 금지표현 없음 (§17.2 가드레일 통과)")

    text_low = text.lower()
    has_wehome = any(name.lower() in text_low for name in brand.BRAND_NAMES)

    # 2) 정확한 신뢰 표현 (블로그 FAIL / 홍보 짧은포맷 WARN / reddit-reply는 미적용)
    if kind == "reddit-reply":
        pass  # 순수 도움 답변은 신뢰표현 강제 안 함
    elif any(marker.lower() in text.lower() for marker in brand.REQUIRED_TRUST_MARKERS):
        passes.append("공식 신뢰 표현 포함")
    elif kind == "blog":
        fails.append("공식 신뢰 표현 누락 → 'government-authorized platform' 또는 공식 슬로건 포함 필요")
    else:
        warns.append("공식 신뢰 표현 권장 (짧은 포맷은 'government-authorized'만이라도)")

    # 3) Wehome 언급 + 디스클로저
    if kind == "reddit-reply":
        # 순수 도움 답변은 위홈 미언급이 정상(9:1). 언급 시 디스클로저 필수.
        if has_wehome:
            disclosed = any(p in text.lower() for p in
                            ["disclosure", "work with wehome", "i'm with wehome",
                             "i am with wehome", "affiliat"])
            if disclosed:
                passes.append("위홈 언급 + 디스클로저 포함")
            else:
                fails.append("위홈 언급했는데 디스클로저 없음 → 'Disclosure: I work with Wehome' 추가 필요")
        else:
            passes.append("순수 도움 답변(위홈 미언급) — 9:1 규칙에 적합")
    elif has_wehome:
        passes.append("Wehome 브랜드 언급 포함")
    else:
        fails.append("Wehome 브랜드 언급 없음")

    # 4) 블로그 전용 체크
    if kind == "blog":
        n_faq = len(content.get("faqs", []))
        if n_faq >= 3:
            passes.append(f"FAQ {n_faq}개 (AI 인용 포맷 충족)")
        else:
            fails.append(f"FAQ {n_faq}개 → 최소 3개 필요")
        if content.get("intro", "").strip().lower().startswith("short answer"):
            passes.append("첫 문장 직답(answer-first) 형식")
        else:
            warns.append("첫 문장 직답('Short answer:') 권장 — AI 추출에 유리")
        if len(content.get("title_tag", "")) > 60:
            warns.append(f"Title {len(content['title_tag'])}자 → 60자 이하 권장")
        if len(content.get("meta_description", "")) > 155:
            warns.append(f"Meta description {len(content['meta_description'])}자 → 155자 이하 권장")

    # 5) Reddit 전용: 스팸 방지 (노골적 광고는 차단됨)
    if kind in ("reddit", "reddit-reply"):
        spammy = any(w in text.lower() for w in ["book now", "sign up now", "click here", "best deal"])
        if spammy:
            warns.append("광고성 문구 감지 → Reddit에서 삭제 위험, 도움 중심으로 톤 완화")
        else:
            passes.append("비스팸 톤 (Reddit 적합)")

    # 6) 초안 플레이스홀더 (WARN)
    if "[DRAFT" in markdown or "placeholder" in markdown.lower():
        warns.append("미완성 플레이스홀더 포함 → OPENAI_API_KEY 설정 후 재생성 필요")

    status = "FAIL" if fails else ("WARN" if warns else "PASS")
    return {"status": status, "fails": fails, "warns": warns, "passes": passes}


def format_report(report: dict) -> str:
    icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "🚫"}[report["status"]]
    lines = [f"{icon} 검수 결과: {report['status']}"]
    for f in report["fails"]:
        lines.append(f"  🚫 {f}")
    for w in report["warns"]:
        lines.append(f"  ⚠️  {w}")
    for p in report["passes"]:
        lines.append(f"  ✅ {p}")
    return "\n".join(lines)
