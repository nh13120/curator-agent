# Google Calendar setup (one time, about 10 minutes)

Curator reads and writes your calendar through a small Python tool
(`tools/gcal.py`) using a desktop OAuth client. You sign in once in your
browser; the token is stored in `config/google_token.json`, which is gitignored.
No password ever passes through Curator.

Account: **your Google account** (decided at kickoff).

## 1. Create a Google Cloud project and enable the Calendar API

1. Open https://console.cloud.google.com/ signed in as your Google account.
2. Top bar → project picker → **New project**. Name it `curator`. Create, then select it.
3. Left menu → **APIs & Services → Library**. Search "Google Calendar API" → **Enable**.

## 2. Configure the OAuth consent screen

1. **APIs & Services → OAuth consent screen** (Google now calls this "Google Auth Platform → Branding").
2. Audience: **External**. App name `Curator`, support email and developer email: your address. Save.
3. **Audience → Test users → Add users**: add your Google account. This keeps the app in
   "Testing" mode, which is all a personal tool needs. (Testing-mode refresh tokens expire after
   7 days only if the scopes are sensitive and the app is unverified; the Calendar scope is
   sensitive, so if the token stops refreshing after a week, re-run step 4. Publishing the app
   to "In production" removes that limit without a review for personal use.)

## 3. Create the desktop OAuth client

1. **APIs & Services → Credentials → Create credentials → OAuth client ID**.
2. Application type: **Desktop app**. Name `curator-desktop`. Create.
3. **Download JSON**. Save it as `config/google_client_secret.json` in this project.
   It is gitignored. Do not paste its contents anywhere.

## 4. Authorize once

```bash
cd "<repo>"
CURATOR_MODE=dry python3 tools/gcal.py auth
```

A browser window opens; choose your Google account, accept the "unverified app"
warning (it's your own app), grant calendar access. The tool prints
`"ok": true` and writes `config/google_token.json`.

## 5. Check

```bash
CURATOR_MODE=dry python3 tools/gcal.py list --from 2026-10-26 --to 2026-11-01
```

You should see your real events for that week. Dry mode can read but refuses
to write; the Phase 3 checkpoint will create and delete one tagged test event
in live mode with your go-ahead.

## Which calendar

`primary` by default. To use another calendar of that account, set
`CURATOR_GOOGLE_CALENDAR_ID` in `.env` to that calendar's id (Calendar settings
→ Integrate calendar → Calendar ID).

## Why not the claude.ai Google Calendar connector

It is zero-setup but cannot tag events with extended properties (which Curator
uses to find and remove only its own events), and it cannot be pointed at
fixture data, so the tests and the live runs would use different code paths.
