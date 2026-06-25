from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse, urlunparse
from urllib.request import Request, urlopen


class InstagramAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class InstagramConfig:
    access_token: str
    ig_user_id: str
    graph_api_version: str = "v21.0"


def normalize_instagram_url(url: str) -> str:
    parsed = urlparse(url.strip())
    cleaned = parsed._replace(query="", fragment="")
    return urlunparse(cleaned)


def extract_instagram_shortcode(url: str) -> str:
    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]
    for index, part in enumerate(path_parts):
        if part.lower() in {"p", "reel", "reels", "tv"} and index + 1 < len(path_parts):
            return path_parts[index + 1]

    query = parse_qs(parsed.query)
    if "shortcode" in query and query["shortcode"]:
        return query["shortcode"][0]

    return path_parts[-1] if path_parts else ""


class InstagramGraphClient:
    def __init__(self, config: InstagramConfig) -> None:
        self.config = config

    @property
    def base_url(self) -> str:
        return f"https://graph.facebook.com/{self.config.graph_api_version}"

    def _request_json(self, path: str, params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        query_params = dict(params or {})
        query_params["access_token"] = self.config.access_token

        query = "&".join(f"{key}={_encode_query_value(value)}" for key, value in query_params.items())
        request = Request(f"{self.base_url}/{path}?{query}", headers={"Accept": "application/json"})

        try:
            with urlopen(request, timeout=30) as response:
                payload = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
            raise InstagramAPIError(f"Instagram Graph API request failed: {detail}") from exc
        except URLError as exc:
            raise InstagramAPIError(f"Instagram Graph API network error: {exc.reason}") from exc

        try:
            data = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise InstagramAPIError("Instagram Graph API returned invalid JSON.") from exc

        if isinstance(data, dict) and data.get("error"):
            error = data["error"]
            message = error.get("message") if isinstance(error, dict) else str(error)
            raise InstagramAPIError(f"Instagram Graph API error: {message}")

        if not isinstance(data, dict):
            raise InstagramAPIError("Instagram Graph API response was not an object.")

        return data

    def list_media(self, fields: Optional[str] = None) -> List[Dict[str, Any]]:
        field_list = fields or "id,caption,media_type,media_url,permalink,thumbnail_url,timestamp,like_count,comments_count"
        data = self._request_json(
            f"{self.config.ig_user_id}/media",
            params={"fields": field_list, "limit": "100"},
        )
        return list(data.get("data", []))

    def list_media_all(self, fields: Optional[str] = None, max_items: Optional[int] = None) -> List[Dict[str, Any]]:
        field_list = fields or "id,caption,media_type,media_url,permalink,thumbnail_url,timestamp,like_count,comments_count"
        items: List[Dict[str, Any]] = []
        after: Optional[str] = None

        while True:
            params: Dict[str, str] = {"fields": field_list, "limit": "100"}
            if after:
                params["after"] = after

            data = self._request_json(f"{self.config.ig_user_id}/media", params=params)
            page_items = list(data.get("data", []))
            items.extend(page_items)

            if max_items is not None and len(items) >= max_items:
                return items[:max_items]

            paging = data.get("paging", {})
            cursors = paging.get("cursors", {}) if isinstance(paging, dict) else {}
            after = cursors.get("after") if isinstance(cursors, dict) else None

            if not after:
                break

        return items

    def get_media_insights(self, media_id: str, metrics: Optional[Iterable[str]] = None) -> Dict[str, Any]:
        metric_names = list(metrics or self._default_metrics())
        return self._request_insights_with_fallback(media_id, metric_names)

    def _request_insights_with_fallback(self, media_id: str, metric_names: List[str]) -> Dict[str, Any]:
        metric_list = ",".join(metric_names)
        try:
            return self._request_json(f"{media_id}/insights", params={"metric": metric_list})
        except InstagramAPIError as exc:
            for fallback_metrics in (self._safe_metrics(), self._minimal_metrics()):
                if metric_names == fallback_metrics:
                    continue
                try:
                    return self._request_json(f"{media_id}/insights", params={"metric": ",".join(fallback_metrics)})
                except InstagramAPIError:
                    continue
            raise exc

    def _default_metrics(self) -> List[str]:
        return [
            "views",
            "likes",
            "comments",
            "shares",
            "saved",
            "total_interactions",
            "ig_reels_avg_watch_time",
            "ig_reels_video_view_total_time",
        ]

    def _safe_metrics(self) -> List[str]:
        return [
            "views",
            "likes",
            "comments",
            "shares",
            "saved",
            "total_interactions",
        ]

    def _minimal_metrics(self) -> List[str]:
        return ["views", "likes", "comments", "shares", "saved"]

    def get_media(self, media_id: str) -> Dict[str, Any]:
        fields = "id,caption,media_type,media_url,permalink,thumbnail_url,timestamp,like_count,comments_count"
        return self._request_json(media_id, params={"fields": fields})


def _encode_query_value(value: str) -> str:
    from urllib.parse import quote

    return quote(str(value), safe="")


def _first_metric_value(insights: Dict[str, Any], metric_names: Iterable[str]) -> float:
    entries = insights.get("data", [])
    if not isinstance(entries, list):
        return 0.0

    for metric_name in metric_names:
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("name") == metric_name:
                values = entry.get("values", [])
                if values and isinstance(values, list):
                    value = values[0].get("value") if isinstance(values[0], dict) else None
                    try:
                        return float(value)
                    except (TypeError, ValueError):
                        return 0.0
    return 0.0


def _find_media_by_permalink(media_items: List[Dict[str, Any]], normalized_url: str, shortcode: str) -> Optional[Dict[str, Any]]:
    for item in media_items:
        permalink = normalize_instagram_url(str(item.get("permalink", "")))
        if permalink == normalized_url:
            return item

    if shortcode:
        for item in media_items:
            permalink = str(item.get("permalink", ""))
            if shortcode in permalink:
                return item
    return None


def _build_record_from_media(
    match: Dict[str, Any],
    media_detail: Dict[str, Any],
    insights: Dict[str, Any],
    config: InstagramConfig,
    source_url: Optional[str] = None,
) -> Dict[str, Any]:
    views = _first_metric_value(insights, ("views", "video_views", "plays", "impressions", "reach", "total_views"))
    likes = _first_metric_value(insights, ("likes", "total_likes"))
    comments = _first_metric_value(insights, ("comments", "total_comments", "replies"))
    shares = _first_metric_value(insights, ("shares", "reposts"))
    saved = _first_metric_value(insights, ("saved",))
    avg_watch_time = _first_metric_value(insights, ("ig_reels_avg_watch_time",))
    total_watch_time = _first_metric_value(insights, ("ig_reels_video_view_total_time",))

    like_count = media_detail.get("like_count", match.get("like_count", 0)) or likes
    comments_count = media_detail.get("comments_count", match.get("comments_count", 0)) or comments
    shares_count = shares or saved
    watch_time_avg = avg_watch_time or total_watch_time

    permalink = str(media_detail.get("permalink") or match.get("permalink") or source_url or "")

    return {
        "source_url": source_url or permalink,
        "video_id": str(media_detail.get("id") or match.get("id") or extract_instagram_shortcode(permalink)),
        "property_id": f"instagram:{config.ig_user_id}",
        "platform": "Instagram Reels" if str(media_detail.get("media_type", "")).upper() in {"VIDEO", "REELS"} else "Instagram",
        "caption_style": "unknown",
        "bgm_style": "unknown",
        "thumbnail_type": "unknown",
        "views": views,
        "likes": like_count,
        "comments": comments_count,
        "shares": shares_count,
        "watch_time_avg": watch_time_avg,
        "video_length": 0,
        "posted_at": media_detail.get("timestamp", match.get("timestamp", "")),
        "instagram_media_id": str(media_detail.get("id") or match.get("id") or ""),
        "instagram_shortcode": extract_instagram_shortcode(permalink),
        "instagram_insights": insights,
    }


def fetch_instagram_metrics_from_url(
    url: str,
    config: InstagramConfig,
    client: Optional[InstagramGraphClient] = None,
) -> Dict[str, Any]:
    normalized_url = normalize_instagram_url(url)
    shortcode = extract_instagram_shortcode(url)
    graph_client = client or InstagramGraphClient(config)

    media_items = graph_client.list_media()
    match = _find_media_by_permalink(media_items, normalized_url, shortcode)
    if not match:
        raise InstagramAPIError(
            "Could not find a matching Instagram media item in the authorized account's media list."
        )

    media_id = str(match.get("id", ""))
    media_detail = graph_client.get_media(media_id)
    insights = graph_client.get_media_insights(media_id)
    return _build_record_from_media(match, media_detail, insights, config, source_url=normalized_url)


def fetch_instagram_metrics_for_account(
    config: InstagramConfig,
    client: Optional[InstagramGraphClient] = None,
    max_items: Optional[int] = None,
) -> List[Dict[str, Any]]:
    graph_client = client or InstagramGraphClient(config)
    media_items = graph_client.list_media_all(max_items=max_items)
    records: List[Dict[str, Any]] = []

    for item in media_items:
        media_id = str(item.get("id", ""))
        if not media_id:
            continue

        media_detail = graph_client.get_media(media_id)
        insights = graph_client.get_media_insights(media_id)
        records.append(_build_record_from_media(item, media_detail, insights, config))

    return records
