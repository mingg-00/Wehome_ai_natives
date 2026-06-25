import json
import os
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from src.analyzer import classify_grade, classify_performance_label
from src.discord_bot import (
    BotServices,
    _evaluate_account,
    _evaluate_video,
    _format_help_text,
    _parse_account_limit,
    _get_sync_guild,
    create_bot,
)
from src.discord_notifier import build_report_message
from src.feedback_generator import generate_feedback
from src.ingest import extract_video_id_from_url, infer_platform_from_url, normalize_platform_name, prepare_records
from src.insight_generator import generate_insights
from src.kpi_summary import generate_kpi_summary
from src.instagram_client import (
    InstagramConfig,
    fetch_instagram_metrics_for_account,
    fetch_instagram_metrics_from_url,
    normalize_instagram_url,
)
from src.main import build_report, load_dotenv_file, load_metrics
from src.youtube_client import (
    YouTubeConfig,
    extract_youtube_video_id,
    fetch_youtube_metrics_for_account,
    fetch_youtube_metrics_from_url,
    normalize_youtube_url,
    parse_iso8601_duration,
)
from src.scorer import (
    calculate_completion_rate,
    calculate_cps,
    calculate_engagement_rate,
    calculate_share_rate,
    score_video,
)


def test_score_video_handles_zero_values() -> None:
    result = score_video(
        {
            "views": 0,
            "likes": 10,
            "comments": 5,
            "shares": 2,
            "watch_time_avg": 30,
            "video_length": 0,
        }
    )

    assert result == {
        "completion_rate": 0.0,
        "engagement_rate": 0.0,
        "share_rate": 0.0,
        "cps": 0.0,
    }


def test_cps_formula_matches_spec() -> None:
    video = {
        "views": 1000,
        "likes": 400,
        "comments": 200,
        "shares": 100,
        "watch_time_avg": 45,
        "video_length": 60,
    }

    assert calculate_completion_rate(video) == 0.75
    assert calculate_engagement_rate(video) == 0.6
    assert calculate_share_rate(video) == 0.1
    assert calculate_cps(video) == 51.0


def test_classify_grade_thresholds() -> None:
    assert classify_grade(80) == "A"
    assert classify_grade(79.99) == "B"
    assert classify_grade(60) == "B"
    assert classify_grade(59.99) == "C"
    assert classify_grade(40) == "C"
    assert classify_grade(39.99) == "D"


def test_classify_performance_label_thresholds() -> None:
    assert classify_performance_label(80) == "high_performer"
    assert classify_performance_label(65) == "strong_performer"
    assert classify_performance_label(50) == "average_performer"
    assert classify_performance_label(39.99) == "low_performer"


def test_generate_feedback_for_low_performer() -> None:
    feedback = generate_feedback(
        {"video_id": "vid_x", "property_id": "prop_x", "platform": "TikTok"},
        cps=12.3,
        grade="D",
        performance_label="low_performer",
        metrics_breakdown={
            "completion_rate": 0.2,
            "engagement_rate": 0.1,
            "share_rate": 0.0,
        },
    )

    assert feedback["grade"] == "D"
    assert feedback["performance_label"] == "low_performer"
    assert "Shorten video length." in feedback["recommendations"]
    assert "Do not reuse the current creative pattern without changes." in feedback["recommendations"]
    assert "\uc2dc\uccad \uc9c0\uc18d\uc2dc\uac04 \ubd80\uc871" in feedback["weaknesses"]


def test_generate_insights_for_high_performer() -> None:
    insight = generate_insights(
        {"video_id": "video_001"},
        {
            "completion_rate": 0.82,
            "engagement_rate": 0.08,
            "share_rate": 0.03,
            "cps": 82.4,
        },
        grade="A",
        performance_label="high_performer",
    )

    assert insight == {
        "video_id": "video_001",
        "property_name": "",
        "cps": 82.4,
        "grade": "A",
        "performance_label": "high_performer",
        "strengths": [
            "\ub192\uc740 \uc2dc\uccad \uc9c0\uc18d\uc2dc\uac04",
            "\uc88b\uc740 \ucc38\uc5ec\uc728",
            "\ud655\uc0b0\ub418\ub294 \uacf5\uc720 \ubc18\uc751",
        ],
        "weaknesses": [],
        "recommended_actions": ["\ud604\uc7ac \ud3ec\ub9f7 \uc720\uc9c0"],
    }


def test_generate_kpi_summary_aggregates_reports() -> None:
    summary = generate_kpi_summary(
        [
            {"video_id": "video_001", "cps": 84.5, "grade": "A"},
            {"video_id": "video_002", "cps": 61.2, "grade": "B"},
            {"video_id": "video_003", "cps": 32.4, "grade": "D"},
        ]
    )

    assert summary == {
        "total_videos": 3,
        "average_cps": 59.37,
        "best_video": "video_001",
        "best_video_name": "video_001",
        "best_cps": 84.5,
        "worst_video": "video_003",
        "worst_video_name": "video_003",
        "worst_cps": 32.4,
        "grade_distribution": {"A": 1, "B": 1, "C": 0, "D": 1},
        "platform_distribution": {"Unknown": 3},
    }


def test_build_report_counts_and_rows() -> None:
    records = [
        {
            "video_id": "a",
            "property_id": "p1",
            "platform": "Instagram Reels",
            "caption_style": "benefit_first",
            "bgm_style": "upbeat_pop",
            "thumbnail_type": "before_after",
            "views": 1000,
            "likes": 500,
            "comments": 300,
            "shares": 700,
            "watch_time_avg": 54,
            "video_length": 60,
            "posted_at": "2026-06-01T09:00:00+09:00",
        },
        {
            "video_id": "b",
            "property_id": "p2",
            "platform": "TikTok",
            "caption_style": "question_hook",
            "bgm_style": "lofi_chill",
            "thumbnail_type": "bold_text",
            "views": 1000,
            "likes": 20,
            "comments": 10,
            "shares": 5,
            "watch_time_avg": 18,
            "video_length": 60,
            "posted_at": "2026-06-02T09:00:00+09:00",
        },
    ]

    bundle = build_report(records)

    assert bundle["report"]["summary"]["total_videos"] == 2
    assert bundle["report"]["summary"]["grade_distribution"]["A"] == 1
    assert bundle["report"]["summary"]["platform_distribution"]["Instagram Reels"] == 1
    assert bundle["report"]["summary"]["platform_distribution"]["TikTok"] == 1
    assert "best_video_name" in bundle["report"]["summary"]
    assert len(bundle["report"]["results"]) == 2
    assert len(bundle["feedback"]) == 2
    assert bundle["report"]["results"][0]["grade"] == "A"
    assert bundle["report"]["results"][0]["performance_label"] == "high_performer"
    assert "metrics" in bundle["report"]["results"][0]
    assert "strengths" in bundle["report"]["results"][0]
    assert bundle["report"]["report_type"] == "analytics_report"
    assert "generated_at" in bundle["report"]


def test_build_report_message_summarizes_report() -> None:
    report = {
        "summary": {
            "total_videos": 2,
            "average_cps": 71.2,
            "best_video": "video_001",
            "best_video_name": "\uac15\ub0a8 \uac10\uc131 \uc219\uc18c",
            "best_cps": 84.5,
            "worst_video": "video_002",
            "worst_video_name": "\ud55c\uc625 \uc2a4\ud14c\uc774",
            "worst_cps": 32.4,
            "grade_distribution": {"A": 1, "B": 0, "C": 1, "D": 0},
        },
        "results": [
            {
                "video_id": "video_001",
                "grade": "A",
                "cps": 84.5,
                "strengths": ["\ub192\uc740 \uc2dc\uccad \uc9c0\uc18d\uc2dc\uac04"],
                "weaknesses": [],
            }
        ],
    }

    message = build_report_message(report, [])

    assert "Analytics Agent report" in message
    assert "total_videos: 2" in message
    assert "best_video: \uac15\ub0a8 \uac10\uc131 \uc219\uc18c (84.5)" in message
    assert "top_video: video_001 / A / 84.5" in message


def test_load_metrics_reads_json(tmp_path: Path) -> None:
    path = tmp_path / "sample.json"
    path.write_text(json.dumps([{"video_id": "vid_1"}]), encoding="utf-8")

    data = load_metrics(path)

    assert data == [{"video_id": "vid_1"}]


def test_load_dotenv_file_sets_environment_variables(tmp_path: Path, monkeypatch) -> None:
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "DISCORD_WEBHOOK_URL=https://discord.example/webhook\nMETA_ACCESS_TOKEN='token-123'\n",
        encoding="utf-8",
    )

    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("META_ACCESS_TOKEN", raising=False)

    load_dotenv_file(dotenv)

    assert os.environ["DISCORD_WEBHOOK_URL"] == "https://discord.example/webhook"
    assert os.environ["META_ACCESS_TOKEN"] == "token-123"


def test_parse_account_limit_defaults_and_validates() -> None:
    assert _parse_account_limit("") == 30
    assert _parse_account_limit("5") == 5

    try:
        _parse_account_limit("abc")
    except ValueError as exc:
        assert "whole number" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid limit")


def test_report_help_text_mentions_default_limit() -> None:
    text = _format_help_text()

    assert "/report account [limit]" in text
    assert "/report youtube [limit]" in text
    assert "30" in text
    assert "/help" in text


def test_discord_bot_registers_report_and_help_commands() -> None:
    bot = create_bot()

    assert bot.get_command("report") is not None
    assert bot.get_command("help") is not None
    report_group = bot.tree.get_command("report")
    assert report_group is not None
    assert getattr(report_group, "commands", None) is not None
    assert {command.name for command in report_group.commands} == {"account", "video", "youtube"}
    assert bot.tree.get_command("help") is not None


def test_get_sync_guild_reads_numeric_server_id(monkeypatch) -> None:
    monkeypatch.setenv("DISCORD_GUILD_ID", "123456789012345678")

    guild = _get_sync_guild()

    assert guild is not None
    assert guild.id == 123456789012345678


def test_discord_bot_report_account_uses_default_limit_and_sends_files(monkeypatch) -> None:
    calls = {}

    def fake_fetch_account_metrics(config, max_items=None):
        calls["max_items"] = max_items
        return [
            {
                "video_id": "video_1",
                "property_id": "prop_1",
                "platform": "Instagram Reels",
                "caption_style": "benefit_first",
                "bgm_style": "upbeat_pop",
                "thumbnail_type": "before_after",
                "views": 100,
                "likes": 10,
                "comments": 5,
                "shares": 2,
                "watch_time_avg": 30,
                "video_length": 60,
                "posted_at": "2026-06-22T09:00:00+09:00",
            }
        ]

    def fake_fetch_video_metrics(url, config):
        raise AssertionError("video fetch should not be called")

    class FakeTyping:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeContext:
        def __init__(self):
            self.sent = []

        def typing(self):
            return FakeTyping()

        async def send(self, content=None, files=None):
            self.sent.append(
                {
                    "content": content,
                    "files": [file.filename for file in (files or [])],
                }
            )

    ctx = FakeContext()
    monkeypatch.setenv("META_ACCESS_TOKEN", "token")
    monkeypatch.setenv("META_INSTAGRAM_ACCOUNT_ID", "12345")

    asyncio.run(_evaluate_account(ctx, BotServices(fake_fetch_account_metrics, fake_fetch_video_metrics), 30))

    assert calls["max_items"] == 30
    assert len(ctx.sent) == 1
    assert "SNS account report ready." in ctx.sent[0]["content"]
    assert "analytics_report.json" in ctx.sent[0]["files"]
    assert "feedback_to_video_agent.json" in ctx.sent[0]["files"]
    assert "kpi_summary.json" in ctx.sent[0]["files"]


def test_discord_bot_report_video_strips_angle_brackets(monkeypatch) -> None:
    calls = {}

    def fake_fetch_account_metrics(config, max_items=None):
        raise AssertionError("account fetch should not be called")

    def fake_fetch_video_metrics(url, config):
        calls["url"] = url
        return {
            "video_id": "video_2",
            "property_id": "prop_2",
            "platform": "Instagram Reels",
            "caption_style": "benefit_first",
            "bgm_style": "upbeat_pop",
            "thumbnail_type": "before_after",
            "views": 200,
            "likes": 20,
            "comments": 10,
            "shares": 4,
            "watch_time_avg": 40,
            "video_length": 60,
            "posted_at": "2026-06-22T10:00:00+09:00",
        }

    class FakeTyping:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeContext:
        def __init__(self):
            self.sent = []

        def typing(self):
            return FakeTyping()

        async def send(self, content=None, files=None):
            self.sent.append(
                {
                    "content": content,
                    "files": [file.filename for file in (files or [])],
                }
            )

    ctx = FakeContext()
    monkeypatch.setenv("META_ACCESS_TOKEN", "token")
    monkeypatch.setenv("META_INSTAGRAM_ACCOUNT_ID", "12345")

    asyncio.run(
        _evaluate_video(
            ctx,
            BotServices(fake_fetch_account_metrics, fake_fetch_video_metrics),
            "<https://www.instagram.com/reel/abc123/>",
        )
    )

    assert calls["url"] == "https://www.instagram.com/reel/abc123/"
    assert len(ctx.sent) == 1
    assert "SNS video report ready." in ctx.sent[0]["content"]


def test_discord_bot_help_command_emits_usage() -> None:
    assert "/report account [limit]" in _format_help_text()
    assert "/help" in _format_help_text()


def test_url_helpers_infer_platform_and_video_id() -> None:
    assert infer_platform_from_url("https://www.youtube.com/watch?v=abc123") == "YouTube"
    assert extract_video_id_from_url("https://www.youtube.com/watch?v=abc123") == "abc123"
    assert infer_platform_from_url("https://www.tiktok.com/@user/video/987654321") == "TikTok"
    assert extract_video_id_from_url("https://www.tiktok.com/@user/video/987654321") == "987654321"


def test_youtube_url_helpers_parse_video_ids() -> None:
    assert extract_youtube_video_id("https://www.youtube.com/watch?v=abc123") == "abc123"
    assert extract_youtube_video_id("https://youtu.be/abc123") == "abc123"
    assert extract_youtube_video_id("https://www.youtube.com/shorts/abc123") == "abc123"
    assert normalize_youtube_url("https://www.youtube.com/shorts/abc123?feature=share") == "https://www.youtube.com/watch?v=abc123"
    assert parse_iso8601_duration("PT1M30S") == 90.0


def test_normalize_platform_name_maps_common_aliases() -> None:
    assert normalize_platform_name("instagram") == "Instagram Reels"
    assert normalize_platform_name("YouTube") == "YouTube Shorts"
    assert normalize_platform_name("TikTok") == "TikTok"
    assert normalize_platform_name("X") == "X"


def test_prepare_records_fills_source_url_metadata() -> None:
    records, warnings = prepare_records(
        [
            {
                "source_url": "https://www.youtube.com/watch?v=abc123",
                "property_id": "prop_1",
                "caption_style": "benefit_first",
                "bgm_style": "upbeat_pop",
                "thumbnail_type": "before_after",
                "views": 100,
                "likes": 10,
                "comments": 5,
                "shares": 2,
                "watch_time_avg": 30,
                "video_length": 60,
                "posted_at": "2026-06-22T09:00:00+09:00",
            }
        ]
    )

    assert warnings == []
    assert records[0]["platform"] == "YouTube Shorts"
    assert records[0]["video_id"] == "abc123"


def test_prepare_records_normalizes_platform_names() -> None:
    records, warnings = prepare_records(
        [
            {
                "video_id": "vid_1",
                "property_id": "prop_1",
                "platform": "instagram",
                "caption_style": "benefit_first",
                "bgm_style": "upbeat_pop",
                "thumbnail_type": "before_after",
                "views": 100,
                "likes": 10,
                "comments": 5,
                "shares": 2,
                "watch_time_avg": 30,
                "video_length": 60,
                "posted_at": "2026-06-22T09:00:00+09:00",
            }
        ]
    )

    assert warnings == []
    assert records[0]["platform"] == "Instagram Reels"


def test_normalize_instagram_url_strips_query_and_fragment() -> None:
    assert (
        normalize_instagram_url("https://www.instagram.com/reel/abc123/?utm_source=test#frag")
        == "https://www.instagram.com/reel/abc123/"
    )


def test_fetch_instagram_metrics_from_url_uses_authorized_client() -> None:
    class FakeInstagramClient:
        def list_media(self, fields=None):
            return [
                {
                    "id": "17900000000000000",
                    "permalink": "https://www.instagram.com/reel/abc123/",
                    "media_type": "REELS",
                    "like_count": 123,
                    "comments_count": 45,
                    "timestamp": "2026-06-22T09:00:00+09:00",
                }
            ]

        def get_media(self, media_id):
            return {
                "id": media_id,
                "media_type": "REELS",
                "like_count": 123,
                "comments_count": 45,
                "timestamp": "2026-06-22T09:00:00+09:00",
            }

        def get_media_insights(self, media_id):
            return {
                "data": [
                    {"name": "views", "values": [{"value": 1000}]},
                    {"name": "likes", "values": [{"value": 123}]},
                    {"name": "comments", "values": [{"value": 45}]},
                    {"name": "saved", "values": [{"value": 12}]},
                ]
            }

    record = fetch_instagram_metrics_from_url(
        "https://www.instagram.com/reel/abc123/?utm_source=test",
        InstagramConfig(access_token="token", ig_user_id="12345", graph_api_version="v21.0"),
        client=FakeInstagramClient(),
    )

    assert record["platform"] == "Instagram Reels"
    assert record["video_id"] == "17900000000000000"
    assert record["views"] == 1000.0
    assert record["likes"] == 123
    assert record["comments"] == 45
    assert record["shares"] == 12.0


def test_fetch_instagram_metrics_for_account_batches_all_media() -> None:
    class FakeInstagramClient:
        def __init__(self):
            self.calls = 0

        def list_media_all(self, fields=None, max_items=None):
            return [
                {
                    "id": "17900000000000001",
                    "permalink": "https://www.instagram.com/reel/abc123/",
                    "media_type": "REELS",
                    "like_count": 11,
                    "comments_count": 2,
                    "timestamp": "2026-06-22T09:00:00+09:00",
                },
                {
                    "id": "17900000000000002",
                    "permalink": "https://www.instagram.com/reel/def456/",
                    "media_type": "REELS",
                    "like_count": 22,
                    "comments_count": 4,
                    "timestamp": "2026-06-22T10:00:00+09:00",
                },
            ]

        def get_media(self, media_id):
            return {
                "id": media_id,
                "media_type": "REELS",
                "like_count": 11 if media_id.endswith("1") else 22,
                "comments_count": 2 if media_id.endswith("1") else 4,
                "timestamp": "2026-06-22T09:00:00+09:00",
            }

        def get_media_insights(self, media_id):
            base = 100 if media_id.endswith("1") else 200
            return {
                "data": [
                    {"name": "views", "values": [{"value": base}]},
                    {"name": "saved", "values": [{"value": 7}]},
                ]
            }

    records = fetch_instagram_metrics_for_account(
        InstagramConfig(access_token="token", ig_user_id="12345", graph_api_version="v21.0"),
        client=FakeInstagramClient(),
    )

    assert len(records) == 2
    assert records[0]["video_id"] == "17900000000000001"
    assert records[1]["video_id"] == "17900000000000002"
    assert records[0]["views"] == 100.0
    assert records[1]["views"] == 200.0


def test_fetch_youtube_metrics_from_url_uses_authorized_client() -> None:
    class FakeYouTubeClient:
        def get_authenticated_channel(self):
            return {
                "id": "channel_123",
                "snippet": {"title": "Wehome Channel"},
                "contentDetails": {"relatedPlaylists": {"uploads": "uploads_123"}},
            }

        def list_videos(self, video_ids):
            return [
                {
                    "id": "abc123",
                    "snippet": {"publishedAt": "2026-06-22T09:00:00Z", "title": "Test Short"},
                    "contentDetails": {"duration": "PT45S"},
                    "statistics": {"viewCount": "1000", "likeCount": "120", "commentCount": "33"},
                }
            ]

        def query_video_analytics(self, video_id, published_at=""):
            assert video_id == "abc123"
            return {
                "views": 1000.0,
                "likes": 120.0,
                "comments": 33.0,
                "shares": 12.0,
                "averageViewDuration": 18.0,
                "estimatedMinutesWatched": 300.0,
            }

    record = fetch_youtube_metrics_from_url(
        "https://www.youtube.com/watch?v=abc123&utm_source=test",
        YouTubeConfig(access_token="token"),
        client=FakeYouTubeClient(),
    )

    assert record["platform"] == "YouTube Shorts"
    assert record["video_id"] == "abc123"
    assert record["views"] == 1000.0
    assert record["shares"] == 12.0
    assert record["watch_time_avg"] == 18.0
    assert record["video_length"] == 45.0


def test_fetch_youtube_metrics_for_account_batches_all_media() -> None:
    class FakeYouTubeClient:
        def get_authenticated_channel(self):
            return {
                "id": "channel_123",
                "snippet": {"title": "Wehome Channel"},
                "contentDetails": {"relatedPlaylists": {"uploads": "uploads_123"}},
            }

        def list_uploads_playlist_items(self, playlist_id, max_items=None):
            assert playlist_id == "uploads_123"
            return [
                {"contentDetails": {"videoId": "abc123"}},
                {"contentDetails": {"videoId": "def456"}},
            ]

        def list_videos(self, video_ids):
            return [
                {
                    "id": "abc123",
                    "snippet": {"publishedAt": "2026-06-22T09:00:00Z", "title": "First"},
                    "contentDetails": {"duration": "PT45S"},
                    "statistics": {"viewCount": "100", "likeCount": "10", "commentCount": "3"},
                },
                {
                    "id": "def456",
                    "snippet": {"publishedAt": "2026-06-22T10:00:00Z", "title": "Second"},
                    "contentDetails": {"duration": "PT120S"},
                    "statistics": {"viewCount": "200", "likeCount": "20", "commentCount": "4"},
                },
            ]

        def query_video_analytics(self, video_id, published_at=""):
            base = 100.0 if video_id == "abc123" else 200.0
            return {
                "views": base,
                "likes": base / 10,
                "comments": base / 20,
                "shares": 5.0,
                "averageViewDuration": 15.0,
                "estimatedMinutesWatched": 50.0,
            }

    records = fetch_youtube_metrics_for_account(
        YouTubeConfig(access_token="token"),
        client=FakeYouTubeClient(),
    )

    assert len(records) == 2
    assert records[0]["video_id"] == "abc123"
    assert records[1]["video_id"] == "def456"
    assert records[0]["platform"] == "YouTube Shorts"
    assert records[1]["platform"] == "YouTube"
