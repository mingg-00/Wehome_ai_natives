from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse, parse_qs
from urllib.request import Request, urlopen


class YouTubeAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class YouTubeConfig:
    access_token: str = ""
    client_id: str = ""
    client_secret: str = ""
    refresh_token: str = ""
    api_base: str = "https://www.googleapis.com"
    analytics_base: str = "https://youtubeanalytics.googleapis.com/v2"


def extract_youtube_video_id(url: str) -> str:
    parsed = urlparse(url.strip())
    hostname = parsed.netloc.lower()
    path_parts = [part for part in parsed.path.split("/") if part]

    if "youtu.be" in hostname:
        return path_parts[0] if path_parts else ""

    if "youtube.com" in hostname:
        query = parse_qs(parsed.query)
        if "v" in query and query["v"]:
            return query["v"][0]
        if path_parts and path_parts[0] == "shorts" and len(path_parts) > 1:
            return path_parts[1]
        if path_parts and path_parts[0] in {"embed", "live"} and len(path_parts) > 1:
            return path_parts[1]
        return path_parts[-1] if path_parts else ""

    return ""


def normalize_youtube_url(url: str) -> str:
    video_id = extract_youtube_video_id(url)
    if not video_id:
        return url.strip()
    return f"https://www.youtube.com/watch?v={video_id}"


def parse_iso8601_duration(duration: str) -> float:
    match = re.fullmatch(
        r"P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?",
        duration or "",
    )
    if not match:
        return 0.0

    days = int(match.group("days") or 0)
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    return float(days * 86400 + hours * 3600 + minutes * 60 + seconds)


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _encode_query(params: Dict[str, Any]) -> str:
    filtered = {key: value for key, value in params.items() if value not in {"", None}}
    return urlencode(filtered, doseq=True)


class YouTubeClient:
    def __init__(self, config: YouTubeConfig) -> None:
        self.config = config

    def _access_token(self) -> str:
        if self.config.access_token.strip():
            return self.config.access_token.strip()

        if not (self.config.client_id.strip() and self.config.client_secret.strip() and self.config.refresh_token.strip()):
            raise YouTubeAPIError(
                "YouTube access token is missing. Set YOUTUBE_ACCESS_TOKEN or provide GOOGLE_CLIENT_ID, "
                "GOOGLE_CLIENT_SECRET, and GOOGLE_REFRESH_TOKEN."
            )

        token_url = "https://oauth2.googleapis.com/token"
        payload = urlencode(
            {
                "client_id": self.config.client_id.strip(),
                "client_secret": self.config.client_secret.strip(),
                "refresh_token": self.config.refresh_token.strip(),
                "grant_type": "refresh_token",
            }
        ).encode("utf-8")
        request = Request(
            token_url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
            raise YouTubeAPIError(f"YouTube OAuth token request failed: {detail}") from exc
        except URLError as exc:
            raise YouTubeAPIError(f"YouTube OAuth network error: {exc.reason}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise YouTubeAPIError("YouTube OAuth token response was not valid JSON.") from exc

        access_token = str(data.get("access_token", "") or "").strip()
        if not access_token:
            raise YouTubeAPIError("YouTube OAuth token response did not include an access token.")
        return access_token

    def _request_json(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        *,
        auth: bool = True,
    ) -> Dict[str, Any]:
        query = _encode_query(params or {})
        request_url = f"{url}?{query}" if query else url
        headers = {"Accept": "application/json"}
        if auth:
            headers["Authorization"] = f"Bearer {self._access_token()}"

        request = Request(request_url, headers=headers)

        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace") if exc.fp else str(exc)
            raise YouTubeAPIError(f"YouTube API request failed: {detail}") from exc
        except URLError as exc:
            raise YouTubeAPIError(f"YouTube API network error: {exc.reason}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise YouTubeAPIError("YouTube API returned invalid JSON.") from exc

        if isinstance(data, dict) and data.get("error"):
            raise YouTubeAPIError(f"YouTube API error: {data['error']}")
        if not isinstance(data, dict):
            raise YouTubeAPIError("YouTube API response was not an object.")
        return data

    def get_authenticated_channel(self) -> Dict[str, Any]:
        data = self._request_json(
            f"{self.config.api_base}/youtube/v3/channels",
            params={"part": "id,snippet,contentDetails", "mine": "true", "maxResults": 1},
        )
        items = data.get("items", [])
        if not isinstance(items, list) or not items:
            raise YouTubeAPIError(
                "Could not find the authenticated YouTube channel. "
                "Make sure the OAuth login used the same Google account that owns the channel, "
                "and confirm that the account already has a YouTube channel."
            )
        channel = items[0]
        if not isinstance(channel, dict):
            raise YouTubeAPIError("Invalid channel response from YouTube.")
        return channel

    def list_uploads_playlist_items(self, playlist_id: str, max_items: Optional[int] = None) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        page_token: Optional[str] = None
        limit = max_items or 50

        while len(items) < limit:
            params: Dict[str, Any] = {
                "part": "snippet,contentDetails",
                "playlistId": playlist_id,
                "maxResults": min(50, limit - len(items)),
            }
            if page_token:
                params["pageToken"] = page_token

            data = self._request_json(f"{self.config.api_base}/youtube/v3/playlistItems", params=params)
            page_items = data.get("items", [])
            if isinstance(page_items, list):
                items.extend([item for item in page_items if isinstance(item, dict)])

            page_token = str(data.get("nextPageToken", "") or "").strip() or None
            if not page_token:
                break

        return items[:limit]

    def list_videos(self, video_ids: Iterable[str]) -> List[Dict[str, Any]]:
        ids = [video_id for video_id in video_ids if str(video_id).strip()]
        if not ids:
            return []

        collected: List[Dict[str, Any]] = []
        for offset in range(0, len(ids), 50):
            chunk = ids[offset : offset + 50]
            data = self._request_json(
                f"{self.config.api_base}/youtube/v3/videos",
                params={"part": "id,snippet,contentDetails,statistics", "id": ",".join(chunk)},
            )
            items = data.get("items", [])
            if isinstance(items, list):
                collected.extend([item for item in items if isinstance(item, dict)])
        return collected

    def query_video_analytics(self, video_id: str, published_at: str = "") -> Dict[str, float]:
        metrics = [
            "views",
            "likes",
            "comments",
            "shares",
            "estimatedMinutesWatched",
            "averageViewDuration",
        ]
        fallback_sets = [metrics, [metric for metric in metrics if metric != "shares"], [metric for metric in metrics if metric not in {"shares", "averageViewDuration"}]]

        last_error: Optional[Exception] = None
        for metric_set in fallback_sets:
            params = {
                "ids": "channel==MINE",
                "startDate": _published_date_or_default(published_at),
                "endDate": _today_utc(),
                "metrics": ",".join(metric_set),
                "dimensions": "video",
                "filters": f"video=={video_id}",
            }
            try:
                data = self._request_json(f"{self.config.analytics_base}/reports", params=params)
                headers = data.get("columnHeaders", [])
                rows = data.get("rows", [])
                if not isinstance(headers, list) or not isinstance(rows, list) or not rows:
                    return {}

                row = rows[0]
                if not isinstance(row, list):
                    return {}

                metrics_map: Dict[str, float] = {}
                for index, header in enumerate(headers):
                    if not isinstance(header, dict):
                        continue
                    name = str(header.get("name", "") or "")
                    if not name:
                        continue
                    value = row[index] if index < len(row) else 0
                    try:
                        metrics_map[name] = float(value)
                    except (TypeError, ValueError):
                        metrics_map[name] = 0.0

                return metrics_map
            except YouTubeAPIError as exc:
                last_error = exc
                continue

        if last_error:
            raise last_error
        return {}


def _published_date_or_default(published_at: str) -> str:
    if published_at:
        try:
            return datetime.fromisoformat(published_at.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            pass
    return (date.today() - timedelta(days=365)).isoformat()


def _youtube_platform_label(duration_seconds: float) -> str:
    return "YouTube Shorts" if duration_seconds <= 60 else "YouTube"


def _build_youtube_record(
    channel: Dict[str, Any],
    playlist_item: Dict[str, Any],
    video: Dict[str, Any],
    analytics: Dict[str, float],
) -> Dict[str, Any]:
    snippet = video.get("snippet", {}) if isinstance(video.get("snippet", {}), dict) else {}
    content_details = video.get("contentDetails", {}) if isinstance(video.get("contentDetails", {}), dict) else {}
    statistics = video.get("statistics", {}) if isinstance(video.get("statistics", {}), dict) else {}

    video_id = str(video.get("id") or playlist_item.get("contentDetails", {}).get("videoId") or "")
    published_at = str(snippet.get("publishedAt") or playlist_item.get("contentDetails", {}).get("videoPublishedAt") or "")
    title = str(snippet.get("title") or playlist_item.get("snippet", {}).get("title") or "")
    duration_seconds = parse_iso8601_duration(str(content_details.get("duration", "")))

    views = analytics.get("views")
    if views is None:
        views = float(statistics.get("viewCount", 0) or 0)
    likes = analytics.get("likes")
    if likes is None:
        likes = float(statistics.get("likeCount", 0) or 0)
    comments = analytics.get("comments")
    if comments is None:
        comments = float(statistics.get("commentCount", 0) or 0)
    shares = analytics.get("shares", 0.0)
    watch_time_avg = analytics.get("averageViewDuration", 0.0)
    if not watch_time_avg:
        estimated_minutes = analytics.get("estimatedMinutesWatched", 0.0)
        if views and estimated_minutes:
            watch_time_avg = round((estimated_minutes * 60) / max(views, 1.0), 2)

    channel_snippet = channel.get("snippet", {})
    channel_title = channel_snippet.get("title", "") if isinstance(channel_snippet, dict) else ""

    return {
        "source_url": normalize_youtube_url(f"https://www.youtube.com/watch?v={video_id}"),
        "video_id": video_id,
        "property_id": f"youtube:{str(channel.get('id', ''))}",
        "property_name": str(channel_title or ""),
        "platform": _youtube_platform_label(duration_seconds),
        "caption_style": "unknown",
        "bgm_style": "unknown",
        "thumbnail_type": "unknown",
        "views": float(views or 0.0),
        "likes": float(likes or 0.0),
        "comments": float(comments or 0.0),
        "shares": float(shares or 0.0),
        "watch_time_avg": float(watch_time_avg or 0.0),
        "video_length": float(duration_seconds),
        "posted_at": published_at,
        "youtube_video_id": video_id,
        "youtube_title": title,
        "youtube_analytics": analytics,
    }


def fetch_youtube_metrics_from_url(
    url: str,
    config: YouTubeConfig,
    client: Optional[YouTubeClient] = None,
) -> Dict[str, Any]:
    video_id = extract_youtube_video_id(url)
    if not video_id:
        raise YouTubeAPIError("Could not extract a YouTube video ID from the URL.")

    yt_client = client or YouTubeClient(config)
    channel = yt_client.get_authenticated_channel()
    videos = yt_client.list_videos([video_id])
    if not videos:
        raise YouTubeAPIError("Could not find the requested YouTube video.")

    video = videos[0]
    published_at = str(video.get("snippet", {}).get("publishedAt", "") or "")
    analytics = yt_client.query_video_analytics(video_id, published_at=published_at)
    return _build_youtube_record(channel, {"contentDetails": {"videoId": video_id}}, video, analytics)


def fetch_youtube_metrics_for_account(
    config: YouTubeConfig,
    client: Optional[YouTubeClient] = None,
    max_items: Optional[int] = None,
) -> List[Dict[str, Any]]:
    yt_client = client or YouTubeClient(config)
    channel = yt_client.get_authenticated_channel()
    uploads_playlist_id = str(channel.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads", "") or "")
    if not uploads_playlist_id:
        raise YouTubeAPIError(
            "Authenticated channel does not expose an uploads playlist. "
            "Check that the signed-in account is the channel owner and that YouTube Studio is available."
        )

    playlist_items = yt_client.list_uploads_playlist_items(uploads_playlist_id, max_items=max_items)
    video_ids = []
    for item in playlist_items:
        video_id = str(item.get("contentDetails", {}).get("videoId", "") or "")
        if video_id:
            video_ids.append(video_id)

    videos = yt_client.list_videos(video_ids)
    videos_by_id = {str(video.get("id", "")): video for video in videos if isinstance(video, dict)}

    records: List[Dict[str, Any]] = []
    for item in playlist_items:
        video_id = str(item.get("contentDetails", {}).get("videoId", "") or "")
        if not video_id:
            continue
        video = videos_by_id.get(video_id)
        if not video:
            continue

        published_at = str(video.get("snippet", {}).get("publishedAt", "") or "")
        analytics = yt_client.query_video_analytics(video_id, published_at=published_at)
        records.append(_build_youtube_record(channel, item, video, analytics))

    return records
