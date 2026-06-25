# Google Cloud Checklist For YouTube

Use this checklist before trying YouTube live fetching in the Analytics Agent.

## Project Setup

- [ ] Create or select a Google Cloud project
- [ ] Enable billing if your org requires it for OAuth app testing
- [ ] Enable the YouTube Data API
- [ ] Enable the YouTube Analytics API

## OAuth Setup

- [ ] Configure the OAuth consent screen
- [ ] Add the app name, support email, and developer contact
- [ ] Add test users if the app is still in testing
- [ ] Create an OAuth client ID
- [ ] Choose the correct application type
- [ ] Save the client ID and client secret

## Scope Review

- [ ] `https://www.googleapis.com/auth/youtube.readonly`
- [ ] `https://www.googleapis.com/auth/yt-analytics.readonly`
- [ ] `https://www.googleapis.com/auth/yt-analytics-monetary.readonly` only if needed later

## Token Material

- [ ] Generate a refresh token for long-lived access
- [ ] Confirm the refresh token can be used to mint access tokens
- [ ] Store secrets in `.env`
- [ ] Do not commit secrets to the repository

## App-Level Validation

- [ ] `python src/main.py --youtube-all` works locally
- [ ] `python src/main.py --youtube-url <youtube_url>` works locally
- [ ] Discord `!report youtube` works
- [ ] Discord `/report youtube` works

## Troubleshooting

- [ ] If the app says the channel cannot be read, check the Google account
- [ ] If analytics data is missing, confirm scopes and API enablement
- [ ] If the refresh token fails, re-run OAuth consent and mint a new token
- [ ] If the app is unverified, confirm whether Google requires verification for the requested scopes

## Related Docs

- YouTube OAuth guide: `docs/youtube_oauth_setup.md`
- Demo samples: `docs/youtube_demo_samples.md`
- Integration plan: `docs/social_platform_integration_plan.md`

