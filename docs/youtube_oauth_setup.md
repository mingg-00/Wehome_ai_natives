# YouTube OAuth Setup Guide

This guide covers the minimum setup needed to run YouTube live fetching in the Analytics Agent.

## What The App Uses

The current implementation uses:

- YouTube Data API to fetch channel metadata, uploads playlist items, and video metadata
- YouTube Analytics API to fetch per-video performance metrics
- OAuth 2.0 for private user data

Official references:

- https://developers.google.com/youtube/v3
- https://developers.google.com/youtube/analytics
- https://developers.google.com/youtube/reporting/guides/authorization

## Required Google Cloud Setup

1. Create or select a Google Cloud project.
2. Enable the YouTube Data API.
3. Enable the YouTube Analytics API.
4. Configure the OAuth consent screen.
5. Create an OAuth client ID for a desktop app or web app.
6. Generate an access token, or generate a refresh token flow for long-lived access.

## Recommended Scopes

Use the smallest set that covers the current MVP:

- `https://www.googleapis.com/auth/youtube.readonly`
- `https://www.googleapis.com/auth/yt-analytics.readonly`

Optional, only if you need monetization reports later:

- `https://www.googleapis.com/auth/yt-analytics-monetary.readonly`

## Environment Variables

Set one of these credential strategies:

### Option A: direct access token

- `YOUTUBE_ACCESS_TOKEN`

### Option B: OAuth refresh flow

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_REFRESH_TOKEN`

The app treats either option as valid.

## What The App Does With Those Credentials

1. Calls `channels.list?mine=true` to identify the connected channel.
2. Reads the channel's uploads playlist from `contentDetails.relatedPlaylists.uploads`.
3. Lists recent uploads from `playlistItems.list`.
4. Fetches video metadata from `videos.list`.
5. Queries analytics for each video through the YouTube Analytics API.
6. Normalizes everything into the common analytics record schema.

## Expected Permissions

If the OAuth account cannot access the channel or analytics data, the app will fail with a permission error.

Common causes:

- wrong Google account
- missing scopes
- OAuth consent not completed
- refresh token revoked
- YouTube API not enabled in the project

## Local Validation

After setting credentials, run:

```powershell
python src/main.py --youtube-all
```

Or test a single URL:

```powershell
python src/main.py --youtube-url https://www.youtube.com/watch?v=VIDEO_ID
```

For Discord:

```powershell
.\scripts\run_discord_bot.ps1
```

## Token Helper

If you need to mint a fresh refresh token, run the helper:

```powershell
$env:GOOGLE_CLIENT_ID="your_client_id"
$env:GOOGLE_CLIENT_SECRET="your_client_secret"
python scripts/youtube_oauth_helper.py
```

The helper opens the consent URL, listens on `http://localhost:8080/`, captures the authorization code, exchanges it for tokens, and prints the resulting `refresh_token`.
