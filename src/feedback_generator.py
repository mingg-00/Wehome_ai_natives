from typing import Any, Dict, List

try:
    from insight_generator import generate_insights
except ImportError:  # pragma: no cover - keeps script and package execution both working
    from src.insight_generator import generate_insights


def generate_feedback(
    video: Dict[str, Any],
    cps: float,
    grade: str,
    performance_label: str,
    metrics_breakdown: Dict[str, float],
) -> Dict[str, Any]:
    insights_bundle = generate_insights(
        video,
        metrics_breakdown,
        grade=grade,
        performance_label=performance_label,
    )

    base_feedback = {
        "video_id": video.get("video_id", ""),
        "property_id": video.get("property_id", ""),
        "property_name": video.get("property_name", ""),
        "platform": video.get("platform", ""),
        "cps": round(cps, 2),
        "grade": grade,
        "performance_label": performance_label,
        "metrics_breakdown": {
            "completion_rate": round(metrics_breakdown.get("completion_rate", 0.0), 4),
            "engagement_rate": round(metrics_breakdown.get("engagement_rate", 0.0), 4),
            "share_rate": round(metrics_breakdown.get("share_rate", 0.0), 4),
        },
        "strengths": insights_bundle["strengths"],
        "weaknesses": insights_bundle["weaknesses"],
        "recommended_actions": insights_bundle["recommended_actions"],
        "insights": [],
        "recommendations": [],
        "feedback_for_video_agent": {},
    }

    if grade == "A":
        insights = [
            "This video is a strong creative reference for similar properties.",
            "The current structure is stable across completion, engagement, and sharing.",
        ]
        recommendations = [
            "Keep the current creative pattern.",
            "Reuse the caption, BGM, and thumbnail pattern.",
            "Document this as the benchmark format.",
        ]
        feedback_for_video_agent = {
            "keep": ["caption_style", "bgm_style", "thumbnail_type"],
            "focus": ["extract successful creative pattern", "prioritize for similar properties"],
        }
    elif grade == "B":
        insights = [
            "This video is performing well, but it still has room to improve.",
            "The next version should isolate one change and measure the impact clearly.",
        ]
        recommendations = [
            "Keep the strongest element.",
            "Test one variable only in the next video.",
            "Improve CTA.",
        ]
        feedback_for_video_agent = {
            "keep": ["strongest element"],
            "test": ["one variable only"],
            "improve": ["CTA"],
            "benchmark": ["A-grade videos"],
        }
    elif grade == "C":
        insights = [
            "This video is average and needs a clearer opening and message.",
            "A stronger hook and tighter packaging should improve performance.",
        ]
        recommendations = [
            "Improve the first 3-second hook.",
            "Test a different thumbnail type.",
            "Strengthen the USP message.",
        ]
        feedback_for_video_agent = {
            "improve": ["first 3-second hook", "USP message"],
            "test": ["different thumbnail type"],
            "adjust": ["caption tone"],
        }
    else:
        insights = [
            "This video underperformed and likely needs a new creative direction.",
            "The next version should be shorter, clearer, and more direct.",
        ]
        recommendations = [
            "Shorten video length.",
            "Place the USP in the first 3 seconds.",
            "Change caption style.",
            "Change BGM style.",
            "Improve thumbnail clarity.",
            "Do not reuse the current creative pattern without changes.",
        ]
        feedback_for_video_agent = {
            "change": ["video length", "caption style", "BGM style", "thumbnail clarity"],
            "priority": ["place USP in the first 3 seconds"],
            "avoid": ["reusing the current creative pattern without changes"],
        }

    base_feedback["insights"] = insights
    base_feedback["recommendations"] = recommendations
    base_feedback["feedback_for_video_agent"] = feedback_for_video_agent
    return base_feedback
