from typing import Any, Dict


def _to_float(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _clamp_ratio(value: float) -> float:
    if value < 0:
        return 0.0
    if value > 1:
        return 1.0
    return value


def calculate_completion_rate(video: Dict[str, Any]) -> float:
    watch_time_avg = _to_float(video.get("watch_time_avg"))
    video_length = _to_float(video.get("video_length"))

    if video_length <= 0:
        return 0.0

    return _clamp_ratio(watch_time_avg / video_length)


def calculate_engagement_rate(video: Dict[str, Any]) -> float:
    views = _to_float(video.get("views"))
    likes = _to_float(video.get("likes"))
    comments = _to_float(video.get("comments"))

    if views <= 0:
        return 0.0

    return _clamp_ratio((likes + comments) / views)


def calculate_share_rate(video: Dict[str, Any]) -> float:
    views = _to_float(video.get("views"))
    shares = _to_float(video.get("shares"))

    if views <= 0:
        return 0.0

    return _clamp_ratio(shares / views)


def calculate_cps(video: Dict[str, Any]) -> float:
    completion_rate = calculate_completion_rate(video)
    engagement_rate = calculate_engagement_rate(video)
    share_rate = calculate_share_rate(video)

    cps = completion_rate * 40 + engagement_rate * 30 + share_rate * 30
    cps = max(0.0, min(100.0, cps))
    return round(cps, 2)


def score_video(video: Dict[str, Any]) -> Dict[str, float]:
    completion_rate = round(calculate_completion_rate(video), 4)
    engagement_rate = round(calculate_engagement_rate(video), 4)
    share_rate = round(calculate_share_rate(video), 4)
    cps = calculate_cps(video)

    return {
        "completion_rate": completion_rate,
        "engagement_rate": engagement_rate,
        "share_rate": share_rate,
        "cps": cps,
    }
