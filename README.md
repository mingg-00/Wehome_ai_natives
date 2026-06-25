# Wehome SNS Analytics & Feedback Agent

This project is a Python MVP for analyzing short-form SNS video performance and generating feedback for the next Video Generation Agent.

It runs on local dummy data by default. There are no external databases or ML libraries.

## Purpose

The agent turns SNS metrics into a batch-level analysis report:

`metrics -> CPS -> grade -> insights -> feedback -> next content direction`

For the presentation-ready version, the agent also produces:

- KPI summary for the whole batch
- per-video strengths and weaknesses
- recommended next actions
- Discord bot responses for on-demand report requests

## Folder Structure

```text
analytics-agent/
  data/
    sample_metrics.json
    demo_metrics.json
    demo_metrics_high.json
    demo_metrics_low.json
  src/
    main.py
    discord_bot.py
    scorer.py
    analyzer.py
    ingest.py
    insight_generator.py
    kpi_summary.py
    discord_notifier.py
    feedback_generator.py
    schemas.py
  output/
    analytics_report.json
    feedback_to_video_agent.json
    kpi_summary.json
  scripts/
    run_demo.ps1
    run_discord_bot.ps1
  README.md
```

## CPS

CPS means Content Performance Score.

The score is designed to quickly compare video quality across posts.

### Formula

- `completion_rate = watch_time_avg / video_length`
- `engagement_rate = (likes + comments) / views`
- `share_rate = shares / views`

```text
CPS = completion_rate * 40 + engagement_rate * 30 + share_rate * 30
```

### Grade Criteria

- `cps >= 80` -> `A`
- `cps >= 60 and cps < 80` -> `B`
- `cps >= 40 and cps < 60` -> `C`
- `cps < 40` -> `D`

### Performance Labels

- `A` -> `high_performer`
- `B` -> `strong_performer`
- `C` -> `average_performer`
- `D` -> `low_performer`

## KPI Summary

The batch summary contains:

- `total_videos`
- `average_cps`
- `best_video`
- `best_video_name`
- `best_cps`
- `worst_video`
- `worst_video_name`
- `worst_cps`
- `grade_distribution`
- `platform_distribution`

This is the first slide-ready number set for the presentation.

## Insight Generation

Each video includes simple rule-based explanation fields:

- `strengths`
- `weaknesses`
- `recommended_actions`

Example rules:

- `completion_rate > 0.7` -> `높은 시청 지속시간`
- `engagement_rate > 0.07` -> `좋은 참여율`
- `share_rate < 0.01` -> `공유율 부족`

## Input Data

Each record in `data/sample_metrics.json` should include:

- `video_id`
- `property_id`
- `platform`
- `caption_style`
- `bgm_style`
- `thumbnail_type`
- `views`
- `likes`
- `comments`
- `shares`
- `watch_time_avg`
- `video_length`
- `posted_at`

## Output Files

After running the project, the script saves:

- `output/analytics_report.json`
- `output/feedback_to_video_agent.json`
- `output/kpi_summary.json`

If you run the Discord bot, the agent can send a short summary message and JSON attachments back to the channel.

## How to Run

From the project root:

```powershell
python src/main.py
```

Use a custom input file:

```powershell
python src/main.py --input data/sample_metrics.json
```

Run the presentation demo dataset:

```powershell
python src/main.py --input data/demo_metrics.json
```

Use the helper script:

```powershell
.\scripts\run_demo.ps1
```

Run alternate scenarios:

```powershell
.\scripts\run_demo.ps1 data/demo_metrics_high.json
.\scripts\run_demo.ps1 data/demo_metrics_low.json
```

## Discord Bot

The bot reads commands from a Discord channel and sends the report back to the same channel.

Set these environment variables in `.env`:

- `DISCORD_BOT_TOKEN`
- `DISCORD_BOT_PREFIX`
- `DISCORD_GUILD_ID` if you want slash commands to appear immediately in one server
- `META_ACCESS_TOKEN`
- `META_INSTAGRAM_ACCOUNT_ID`
- `META_GRAPH_API_VERSION`
- `YOUTUBE_ACCESS_TOKEN` or `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`

Note:

- Live URL-based metric fetching is currently implemented for Instagram through the official Graph API.
- Live URL-based metric fetching is also implemented for YouTube through the YouTube Data API and YouTube Analytics API.
- The analysis pipeline itself already accepts normalized records from Instagram Reels, TikTok, and YouTube Shorts.
- See `docs/social_platform_integration_plan.md` for the remaining YouTube/TikTok expansion plan and token checklist.
- See `docs/youtube_oauth_setup.md`, `docs/youtube_demo_samples.md`, and `docs/google_cloud_checklist.md` for the YouTube rollout pack.

Run the bot:

```powershell
.\scripts\run_discord_bot.ps1
```

To mint a fresh YouTube refresh token locally:

```powershell
$env:GOOGLE_CLIENT_ID="your_client_id"
$env:GOOGLE_CLIENT_SECRET="your_client_secret"
python scripts/youtube_oauth_helper.py
```

Commands:

```text
/report account
/report youtube
/report account limit:10
/report youtube limit:10
/report video <url>
/help
```

The bot replies with:

- a compact summary message
- `analytics_report.json`
- `feedback_to_video_agent.json`
- `kpi_summary.json`

Required Discord setup:

1. Create a Discord bot in the Developer Portal.
2. Enable the Message Content Intent if you want prefix fallbacks like `!report`.
3. Invite the bot to your server with permission to read and send messages.
4. Put the bot token in `.env` as `DISCORD_BOT_TOKEN=...`.
5. If `/report` does not appear immediately, set `DISCORD_GUILD_ID` to your server ID and restart the bot so it syncs guild commands instantly.

Account evaluation default:

- `/report account` evaluates the most recent 30 Instagram media items.
- `/report account limit:<n>` overrides that count.
- Valid range: 1-100.

YouTube evaluation default:

- `/report youtube` evaluates the most recent 30 YouTube videos from the connected account.
- `/report youtube limit:<n>` overrides that count.
- Valid range: 1-100.

Note:

- Global slash commands can take time to show up in Discord clients.
- Guild commands update instantly, which is why `DISCORD_GUILD_ID` is the fastest fix when testing.

## MVP Checklist

Use this as the final go-live checklist:

1. `!report account` and `/report account` both return a summary and JSON attachments.
2. `!report youtube` and `/report youtube` both return a summary and JSON attachments.
3. `!report video <url>` and `/report video <url>` both return a summary and JSON attachments.
4. The bot responds in the target Discord channel without manual copying.
5. `DISCORD_GUILD_ID` is set if you need immediate slash command visibility during testing.
6. `.env` contains the Discord bot token, Meta credentials, and YouTube credentials.
7. The bot process stays running during the demo.
8. Failure cases are understandable:
   - invalid Instagram URL
   - invalid YouTube OAuth token
   - missing Meta token
   - missing YouTube token
   - permission issues
   - empty account results

## Smoke Test

Run these in order when validating the release:

1. Start the bot process.
2. In Discord, run `/help`.
3. In Discord, run `/report account`.
4. In Discord, run `/report youtube`.
5. In Discord, run `/report account limit:10`.
6. In Discord, run `/report youtube limit:10`.
7. In Discord, run `/report video <url>`.
8. Confirm the channel receives:
   - a summary message
   - `analytics_report.json`
   - `feedback_to_video_agent.json`
   - `kpi_summary.json`
9. Break one credential on purpose and confirm the error message is understandable.

## CLI Discord Delivery

If you still want to send a summary to a Discord webhook from the CLI:

```powershell
$env:DISCORD_WEBHOOK_URL="<your-discord-webhook-url>"
python src/main.py --input data/demo_metrics.json
```

`python src/main.py` also loads `.env` from the project root automatically, so you can store `DISCORD_WEBHOOK_URL` there instead of exporting it in the shell.

Discord setup:

1. Create a text channel in your Discord server.
2. Create a webhook for that channel.
3. Copy the webhook URL.
4. Put it in `.env` as `DISCORD_WEBHOOK_URL=...` or set the environment variable directly.

## .env Setup

Copy `.env.example` to `.env` and set the Discord bot token plus Meta credentials locally.

```powershell
copy .env.example .env
```

## Tests

```powershell
pytest
```

## Notes

- This is an MVP for an intern project presentation.
- The code is intentionally simple and readable.
- The data is dummy data only.
- `run_demo.ps1` loads `.env` automatically if it exists.
