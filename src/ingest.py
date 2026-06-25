from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any, Dict, Iterable, List, Tuple
from urllib.parse import parse_qs, urlparse


REQUIRED_FIELDS = [
    "video_id",
    "property_id",
    "platform",
    "caption_style",
    "bgm_style",
    "thumbnail_type",
    "views",
    "likes",
    "comments",
    "shares",
    "watch_time_avg",
    "video_length",
    "posted_at",
]

PLATFORM_ALIASES = {
    "instagram": "Instagram Reels",
    "instagram reels": "Instagram Reels",
    "instagram short": "Instagram Reels",
    "youtube": "YouTube Shorts",
    "youtube shorts": "YouTube Shorts",
    "tiktok": "TikTok",
}


def _to_dict(record: Any) -> Dict[str, Any]:
    if is_dataclass(record):
        return asdict(record)
    if isinstance(record, dict):
        return dict(record)
    raise TypeError("Each video record must be a mapping or dataclass instance.")


def infer_platform_from_url(url: str) -> str:
    hostname = urlparse(url).netloc.lower()

    if "youtube.com" in hostname or "youtu.be" in hostname:
        return "YouTube"
    if "tiktok.com" in hostname:
        return "TikTok"
    if "instagram.com" in hostname:
        return "Instagram"
    return "Unknown"


def normalize_platform_name(platform: str) -> str:
    cleaned = str(platform or "").strip()
    if not cleaned:
        return ""

    alias = PLATFORM_ALIASES.get(cleaned.lower())
    if alias:
        return alias

    return cleaned


def extract_video_id_from_url(url: str) -> str:
    parsed = urlparse(url)
    hostname = parsed.netloc.lower()
    path_parts = [part for part in parsed.path.split("/") if part]

    if "youtube.com" in hostname:
        query = parse_qs(parsed.query)
        if "v" in query and query["v"]:
            return query["v"][0]
        if path_parts and path_parts[0] == "shorts" and len(path_parts) > 1:
            return path_parts[1]
        return path_parts[-1] if path_parts else ""

    if "youtu.be" in hostname:
        return path_parts[0] if path_parts else ""

    if "tiktok.com" in hostname or "instagram.com" in hostname:
        for part in path_parts:
            if part.lower() in {"video", "reel", "reels", "p"}:
                next_index = path_parts.index(part) + 1
                if next_index < len(path_parts):
                    return path_parts[next_index]
        return path_parts[-1] if path_parts else ""

    return ""


def normalize_record(record: Any) -> Dict[str, Any]:
    payload = _to_dict(record)
    source_url = str(payload.get("source_url", "") or "")

    if source_url:
        payload.setdefault("platform", normalize_platform_name(infer_platform_from_url(source_url)))
        payload.setdefault("video_id", extract_video_id_from_url(source_url))

    if payload.get("platform"):
        payload["platform"] = normalize_platform_name(str(payload.get("platform", "")))

    for field in ["video_id", "property_id", "platform", "caption_style", "bgm_style", "thumbnail_type", "posted_at"]:
        payload.setdefault(field, "")

    for field in ["views", "likes", "comments", "shares", "watch_time_avg", "video_length"]:
        payload.setdefault(field, 0)

    if source_url:
        payload["source_url"] = source_url

    return payload


def validate_record(record: Dict[str, Any], index: int) -> List[str]:
    issues: List[str] = []

    for field in REQUIRED_FIELDS:
        if field not in record:
            issues.append(f"Record {index + 1}: missing field '{field}'")

    for field in ["video_id", "property_id", "platform", "caption_style", "bgm_style", "thumbnail_type", "posted_at"]:
        if str(record.get(field, "")).strip() == "":
            issues.append(f"Record {index + 1}: field '{field}' cannot be empty")

    for field in ["views", "likes", "comments", "shares", "watch_time_avg", "video_length"]:
        value = record.get(field)
        if not isinstance(value, (int, float)):
            issues.append(f"Record {index + 1}: field '{field}' must be numeric")
            continue
        if value < 0:
            issues.append(f"Record {index + 1}: field '{field}' cannot be negative")

    return issues


def prepare_records(records: Iterable[Any], strict: bool = False) -> Tuple[List[Dict[str, Any]], List[str]]:
    normalized_records: List[Dict[str, Any]] = []
    warnings: List[str] = []

    for index, record in enumerate(records):
        normalized = normalize_record(record)
        issues = validate_record(normalized, index)

        if issues and strict:
            raise ValueError("; ".join(issues))
        if issues:
            warnings.extend(issues)

        normalized_records.append(normalized)

    return normalized_records, warnings
