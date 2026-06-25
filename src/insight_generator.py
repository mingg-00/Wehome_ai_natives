from __future__ import annotations

from typing import Any, Dict, List


def _append_unique(items: List[str], value: str) -> None:
    if value not in items:
        items.append(value)


def generate_insights(
    video: Dict[str, Any],
    metrics_breakdown: Dict[str, float],
    *,
    grade: str,
    performance_label: str,
) -> Dict[str, Any]:
    completion_rate = float(metrics_breakdown.get("completion_rate", 0.0))
    engagement_rate = float(metrics_breakdown.get("engagement_rate", 0.0))
    share_rate = float(metrics_breakdown.get("share_rate", 0.0))
    cps = round(float(metrics_breakdown.get("cps", 0.0)), 2)
    caption_style = str(video.get("caption_style", "") or "").strip()
    bgm_style = str(video.get("bgm_style", "") or "").strip()
    thumbnail_type = str(video.get("thumbnail_type", "") or "").strip()

    strengths: List[str] = []
    weaknesses: List[str] = []
    recommended_actions: List[str] = []

    if completion_rate > 0.7:
        _append_unique(strengths, "높은 시청 지속시간")
    if engagement_rate > 0.07:
        _append_unique(strengths, "좋은 참여율")
    if share_rate > 0.02:
        _append_unique(strengths, "확산되는 공유 반응")

    if completion_rate < 0.5:
        _append_unique(weaknesses, "시청 지속시간 부족")
    if engagement_rate < 0.03:
        _append_unique(weaknesses, "참여율 부족")
    if share_rate < 0.01:
        _append_unique(weaknesses, "공유율 부족")

    if caption_style in {"benefit_first", "problem_solution", "direct_cta"} and completion_rate >= 0.6:
        _append_unique(strengths, "메시지 구조가 명확함")
    if thumbnail_type in {"before_after", "property_view"} and share_rate >= 0.02:
        _append_unique(strengths, "썸네일과 콘텐츠 연결이 좋음")
    if bgm_style in {"upbeat_pop", "trending_audio"} and engagement_rate >= 0.05:
        _append_unique(strengths, "배경음이 반응을 잘 끌어냄")

    if caption_style in {"story_driven", "listicle"} and completion_rate < 0.6:
        _append_unique(weaknesses, "오프닝 메시지 강화 필요")
    if thumbnail_type in {"bold_text", "location_text"} and share_rate < 0.02:
        _append_unique(weaknesses, "썸네일 훅 보강 필요")

    if grade == "A" and not weaknesses:
        recommended_actions.append("현재 포맷 유지")
    elif grade == "A":
        recommended_actions.append("강점은 유지하고 공유 확산 요소를 보완")
    elif grade == "B":
        recommended_actions.append("강점은 유지하고 약점 1가지만 개선")
    elif grade == "C":
        recommended_actions.append("오프닝 훅과 CTA를 함께 개선")
    else:
        recommended_actions.append("콘셉트를 새로 설계하고 짧은 훅부터 다시 테스트")

    if "공유율 부족" in weaknesses:
        _append_unique(recommended_actions, "공유를 유도하는 CTA 추가")
    if "참여율 부족" in weaknesses:
        _append_unique(recommended_actions, "댓글 유도 질문을 앞부분에 배치")
    if "시청 지속시간 부족" in weaknesses:
        _append_unique(recommended_actions, "첫 3초 훅을 더 강하게 수정")
    if "오프닝 메시지 강화 필요" in weaknesses:
        _append_unique(recommended_actions, "핵심 메시지를 3초 안에 전달")
    if "썸네일 훅 보강 필요" in weaknesses:
        _append_unique(recommended_actions, "썸네일의 첫 인상을 더 강하게 설계")

    return {
        "video_id": video.get("video_id", ""),
        "property_name": video.get("property_name", ""),
        "cps": cps,
        "grade": grade,
        "performance_label": performance_label,
        "strengths": strengths,
        "weaknesses": weaknesses,
        "recommended_actions": recommended_actions,
    }
