from __future__ import annotations

from typing import Any, Dict, List


def generate_kpi_summary(reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_videos = len(reports)
    grade_distribution = {"A": 0, "B": 0, "C": 0, "D": 0}
    platform_distribution: Dict[str, int] = {}

    if total_videos == 0:
        return {
            "total_videos": 0,
            "average_cps": 0.0,
            "best_video": "",
            "best_video_name": "",
            "best_cps": 0.0,
            "worst_video": "",
            "worst_video_name": "",
            "worst_cps": 0.0,
            "grade_distribution": grade_distribution,
            "platform_distribution": platform_distribution,
        }

    total_cps = 0.0
    best_report: Dict[str, Any] | None = None
    worst_report: Dict[str, Any] | None = None

    for report in reports:
        cps = float(report.get("cps", 0.0))
        grade = str(report.get("grade", "D")).upper()
        video_id = str(report.get("video_id", ""))
        property_name = str(report.get("property_name", "") or "").strip()
        display_name = property_name or video_id
        platform = str(report.get("platform", "") or "").strip() or "Unknown"

        total_cps += cps
        if grade in grade_distribution:
            grade_distribution[grade] += 1
        platform_distribution[platform] = platform_distribution.get(platform, 0) + 1

        if best_report is None or cps > float(best_report.get("cps", 0.0)):
            best_report = {"video_id": video_id, "display_name": display_name, "cps": cps}
        if worst_report is None or cps < float(worst_report.get("cps", 0.0)):
            worst_report = {"video_id": video_id, "display_name": display_name, "cps": cps}

    average_cps = round(total_cps / total_videos, 2)

    return {
        "total_videos": total_videos,
        "average_cps": average_cps,
        "best_video": best_report["video_id"] if best_report else "",
        "best_video_name": best_report["display_name"] if best_report else "",
        "best_cps": round(best_report["cps"], 2) if best_report else 0.0,
        "worst_video": worst_report["video_id"] if worst_report else "",
        "worst_video_name": worst_report["display_name"] if worst_report else "",
        "worst_cps": round(worst_report["cps"], 2) if worst_report else 0.0,
        "grade_distribution": grade_distribution,
        "platform_distribution": platform_distribution,
    }
