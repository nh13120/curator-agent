#!/bin/bash
# One-time (or whenever a login expires): open Chrome on Curator's own browser
# profile so you can sign in to Eventbrite and similar sites yourself. Curator
# reuses this profile through the Playwright MCP server (.mcp.json) and never
# sees or types a password.
#
# Usage: bin/browser-login.sh
# Then: sign in to Eventbrite AND Luma (both tabs open), then quit Chrome (Cmd-Q).
# A Luma session is what lets Curator cancel a Luma registration later.
#
# Note: only one Chrome instance can use the profile at a time. Quit this
# window before a Curator run starts, or the run cannot open the browser.

set -e
PROFILE="$HOME/Library/Application Support/curator/chrome-profile"
mkdir -p "$PROFILE"
echo "Opening Chrome with Curator's profile: $PROFILE"
echo "Sign in to Eventbrite (and any other RSVP sites), then quit Chrome."
exec "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
  --user-data-dir="$PROFILE" \
  --no-first-run --no-default-browser-check \
  "https://www.eventbrite.com/signin/" "https://luma.com/signin"
