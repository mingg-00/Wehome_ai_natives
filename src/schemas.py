from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class VideoMetric:
    video_id: str
    property_id: str
    platform: str
    caption_style: str
    bgm_style: str
    thumbnail_type: str
    views: int
    likes: int
    comments: int
    shares: int
    watch_time_avg: float
    video_length: float
    posted_at: str


@dataclass
class FeedbackResult:
    video_id: str
    property_id: str
    platform: str
    performance_score: float
    grade: str
    insights: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    feedback_for_video_agent: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalyticsReport:
    total_videos: int
    high_performers: int
    average_performers: int
    low_performers: int
    results: List[Dict[str, Any]] = field(default_factory=list)
