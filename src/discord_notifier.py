from __future__ import annotations

import json
from typing import Any, Dict, List
from urllib import error, parse, request


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def build_report_message(report: Dict[str, Any], feedback: List[Dict[str, Any]]) -> str:
    summary = report.get("summary", {})
    distribution = summary.get("grade_distribution", {})
    results = report.get("results", [])
    top_result = max(results, key=lambda row: float(row.get("cps", 0.0)), default={})

    lines = [
        "Analytics Agent report",
        f"- total_videos: {summary.get('total_videos', 0)}",
        f"- average_cps: {summary.get('average_cps', 0)}",
        f"- best_video: {summary.get('best_video_name', summary.get('best_video', ''))} ({summary.get('best_cps', 0)})",
        f"- worst_video: {summary.get('worst_video_name', summary.get('worst_video', ''))} ({summary.get('worst_cps', 0)})",
        f"- grade_distribution: A {distribution.get('A', 0)}, B {distribution.get('B', 0)}, C {distribution.get('C', 0)}, D {distribution.get('D', 0)}",
    ]

    platform_distribution = summary.get("platform_distribution", {})
    if isinstance(platform_distribution, dict) and platform_distribution:
        platform_parts = ", ".join(f"{name} {count}" for name, count in sorted(platform_distribution.items()))
        lines.append(f"- platform_distribution: {platform_parts}")

    if top_result:
        strengths = top_result.get("strengths", [])
        weaknesses = top_result.get("weaknesses", [])
        lines.append(
            f"- top_video: {top_result.get('video_id', '')} / {top_result.get('grade', '')} / {top_result.get('cps', 0)}"
        )
        if strengths:
            lines.append(f"- top_strengths: {', '.join(strengths[:3])}")
        if weaknesses:
            lines.append(f"- top_weaknesses: {', '.join(weaknesses[:3])}")

    return "\n".join(lines)


def send_discord_webhook(webhook_url: str, content: str, thread_name: str = "") -> None:
    payload = json.dumps({"content": _truncate(content, 1900)}).encode("utf-8")
    if thread_name.strip():
        parsed = parse.urlsplit(webhook_url)
        query = dict(parse.parse_qsl(parsed.query, keep_blank_values=True))
        query["thread_name"] = thread_name.strip()
        query["wait"] = "true"
        webhook_url = parse.urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, parse.urlencode(query), parsed.fragment)
        )
    else:
        parsed = parse.urlsplit(webhook_url)
        query = dict(parse.parse_qsl(parsed.query, keep_blank_values=True))
        query["wait"] = "true"
        webhook_url = parse.urlunsplit(
            (parsed.scheme, parsed.netloc, parsed.path, parse.urlencode(query), parsed.fragment)
        )

    req = request.Request(
        webhook_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "WehomeAnalyticsAgent/1.0",
        },
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=15) as response:
            if response.status >= 400:
                raise RuntimeError(f"Discord webhook returned HTTP {response.status}")
    except error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            body = ""
        detail = f": {body}" if body else ""
        raise RuntimeError(f"Discord webhook returned HTTP {exc.code}{detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Failed to send Discord webhook: {exc.reason}") from exc
