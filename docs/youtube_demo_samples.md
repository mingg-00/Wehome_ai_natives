# YouTube Demo Samples

This file shows the sample input shape and the expected output shape for a YouTube record in the Analytics Agent.

## Sample Input Record

The analyzer accepts normalized records, so the raw YouTube response is converted into the same schema used by Instagram and the demo JSON files.

```json
{
  "source_url": "https://www.youtube.com/watch?v=abc123",
  "video_id": "abc123",
  "property_id": "youtube:channel_123",
  "property_name": "Wehome Channel",
  "platform": "YouTube Shorts",
  "caption_style": "unknown",
  "bgm_style": "unknown",
  "thumbnail_type": "unknown",
  "views": 12400,
  "likes": 840,
  "comments": 96,
  "shares": 41,
  "watch_time_avg": 18.4,
  "video_length": 45,
  "posted_at": "2026-06-22T09:00:00Z",
  "youtube_video_id": "abc123",
  "youtube_title": "How to evaluate a property in 30 seconds",
  "youtube_analytics": {
    "views": 12400,
    "likes": 840,
    "comments": 96,
    "shares": 41,
    "averageViewDuration": 18.4,
    "estimatedMinutesWatched": 3804
  }
}
```

## What The Report Will Add

After `prepare_records`, scoring and reporting append these fields:

- `completion_rate`
- `engagement_rate`
- `share_rate`
- `cps`
- `grade`
- `performance_label`
- `metrics`
- `strengths`
- `weaknesses`
- `recommended_actions`

## Example Output Fragment

### `output/analytics_report.json`

```json
{
  "report_type": "analytics_report",
  "summary": {
    "total_videos": 1,
    "average_cps": 72.14,
    "best_video": "abc123",
    "best_video_name": "Wehome Channel",
    "best_cps": 72.14,
    "worst_video": "abc123",
    "worst_video_name": "Wehome Channel",
    "worst_cps": 72.14,
    "grade_distribution": {
      "A": 0,
      "B": 1,
      "C": 0,
      "D": 0
    },
    "platform_distribution": {
      "YouTube Shorts": 1
    }
  }
}
```

### `output/feedback_to_video_agent.json`

```json
[
  {
    "video_id": "abc123",
    "platform": "YouTube Shorts",
    "grade": "B",
    "performance_label": "strong_performer",
    "recommendations": [
      "Keep the strongest element.",
      "Test one variable only in the next video.",
      "Improve CTA."
    ]
  }
]
```

### `output/kpi_summary.json`

```json
{
  "total_videos": 1,
  "average_cps": 72.14,
  "best_video": "abc123",
  "best_video_name": "Wehome Channel",
  "best_cps": 72.14,
  "worst_video": "abc123",
  "worst_video_name": "Wehome Channel",
  "worst_cps": 72.14,
  "grade_distribution": {
    "A": 0,
    "B": 1,
    "C": 0,
    "D": 0
  },
  "platform_distribution": {
    "YouTube Shorts": 1
  }
}
```

## Demo Command

```powershell
python src/main.py --youtube-url https://www.youtube.com/watch?v=abc123
```

If you only want to demo the analysis layer, you can also drop the record into a local JSON file and run:

```powershell
python src/main.py --input data/sample_metrics.json
```

