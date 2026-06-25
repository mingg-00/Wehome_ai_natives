# Social Platform Integration Plan

## Goal

Extend the Analytics Agent from Instagram-only live fetching to a multi-platform SNS ingestion layer without changing the scoring and reporting pipeline.

The current pipeline already works on normalized records:

`raw platform payload -> normalize_record -> prepare_records -> score -> insights -> feedback -> report`

That means the implementation risk is concentrated in the platform-specific fetchers, not in the analyzer.

## Current State

Already working:

- Batch analytics and reporting
- CPS scoring
- Insight generation
- Feedback generation
- Discord bot delivery
- Instagram live fetching through the Meta Graph API
- YouTube live fetching through the YouTube Data API and YouTube Analytics API
- Demo input acceptance for Instagram Reels, TikTok, and YouTube Shorts records

Not yet live:

- TikTok live ingestion
- Platform-specific auth/token management outside Instagram

## Recommended Architecture

Keep the existing analysis engine, and add a thin provider layer:

```text
src/
  platforms/
    base.py
    instagram.py
    youtube.py
    tiktok.py
    resolver.py
```

Recommended flow:

1. Resolve platform from URL or account target.
2. Dispatch to the platform connector.
3. Convert raw API response into a common `VideoMetric`-like dict.
4. Pass normalized records into `prepare_records`.
5. Reuse the existing analyzer, insight generator, feedback generator, and Discord delivery.

This keeps platform churn out of the scoring/reporting code.

## YouTube Integration

### Best-fit API choice

Use the YouTube Analytics API for performance metrics and the YouTube Data API for video/channel metadata.

Official docs indicate:

- YouTube Analytics and Reporting APIs use OAuth 2.0 for private user data.
- The Analytics API supports scopes such as `yt-analytics.readonly`.
- The Reporting API also supports `yt-analytics.readonly`.
- Public apps accessing user data may require verification.
- Service accounts are not supported for YouTube Analytics/Reporting user data.

### Required credentials

- Google Cloud project
- Enabled YouTube Data API
- Enabled YouTube Analytics API
- OAuth client ID
- OAuth client secret
- User consent flow
- Refresh token for long-lived access

### Recommended scopes

- `https://www.googleapis.com/auth/youtube.readonly`
- `https://www.googleapis.com/auth/yt-analytics.readonly`
- Optional: `https://www.googleapis.com/auth/yt-analytics-monetary.readonly`

### Suggested use case mapping

- Account-level report: channel/video performance pulled from Analytics API
- Single-video report: video metadata plus analytics query filtered by video ID
- Demo output: normalize to the same record shape already used by the analyzer

### Risks

- OAuth verification may be required for public distribution.
- Access is tied to the signed-in YouTube account or content owner permissions.
- Analytics/reporting data is private user data, so service-account shortcuts are not an option.

## TikTok Integration

### Best-fit API choice

For creator-owned live access, the current official docs expose:

- Login Kit for authentication
- Display API for user info and video listing/query
- Research API for research-oriented access
- Content Posting API for publishing workflows

The Display API currently documents:

- `/v2/user/info/`
- `/v2/video/list/`
- `/v2/video/query/`

and permissions including:

- `user.info.basic`
- `video.list`

### Required credentials

- TikTok developer account
- Registered app
- Client key
- Client secret
- Redirect URI
- User access token
- Refresh flow for token renewal

### Suggested use case mapping

- Account-level report: `video.list` to fetch recent uploaded videos
- Single-video report: `video.query` by video ID
- Profile context: `user.info.basic`

### Important limitation

TikTok's public docs here are a better fit for profile/video metadata than for a universal analytics API equivalent to YouTube Analytics.
If the business needs creator metrics such as watch time, retention, reach, or shares beyond what Display API exposes, that likely needs a separate platform-specific approval path or a product decision about what "live analytics" means for TikTok in this MVP.

## Token / Secret Checklist

### Instagram

- `META_ACCESS_TOKEN`
- `META_INSTAGRAM_ACCOUNT_ID`
- `META_GRAPH_API_VERSION`

### YouTube

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REFRESH_TOKEN`
- `YOUTUBE_CHANNEL_ID` or content-owner mapping
- `YOUTUBE_API_KEY` only if public-only data is needed

### TikTok

- `TIKTOK_CLIENT_KEY`
- `TIKTOK_CLIENT_SECRET`
- `TIKTOK_REDIRECT_URI`
- `TIKTOK_ACCESS_TOKEN`
- `TIKTOK_REFRESH_TOKEN`

## Implementation Order For Today

1. Add a platform connector abstraction.
2. Normalize each provider into the same record schema.
3. Update Discord help text and demo examples.
4. Add tests for URL routing and normalized platform names.

## What Not To Do In This MVP

- Do not replace the current analyzer.
- Do not redesign the report schema.
- Do not introduce a database yet.
- Do not implement infrastructure changes before the live connectors are stable.

## References

- YouTube Analytics and Reporting APIs: https://developers.google.com/youtube/analytics
- YouTube OAuth 2.0 authorization: https://developers.google.com/youtube/reporting/guides/authorization
- YouTube Data API: https://developers.google.com/youtube/v3
- TikTok for Developers overview: https://developers.tiktok.com/doc/overview
- TikTok Login Kit for Web: https://developers.tiktok.com/doc/login-kit-web
- TikTok Display API overview: https://developers.tiktok.com/doc/display-api-overview
