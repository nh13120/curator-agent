# Telegram bot setup (one time, about 5 minutes)

Curator talks to you only through a Telegram bot: bookings, weekly summaries,
questions, rating prompts and alerts go out; your replies, ratings and rule
changes come back. Decided at kickoff: a new, separate bot.

There is no always-on server. Your replies are read at the start of the next
run (the daily check every morning, the weekly plan on Saturday).

## 1. Create the bot

1. In Telegram, open a chat with **@BotFather** and send `/newbot`.
2. Name: `Curator` (display name). Username: something unique ending in `bot`,
   for example `nicolas_curator_bot`.
3. BotFather replies with an HTTP API token. **Do not paste it into chat with me.**
   Put it in `.env`:

   ```
   CURATOR_TELEGRAM_BOT_TOKEN=<the token>
   ```

4. Optional but recommended: send BotFather `/setprivacy` → your bot → **Disable**
   is NOT needed (the bot only runs in your private chat). Leave defaults.

## 2. Tell the bot who you are

1. Open your new bot in Telegram and send it any message, for example `hello`.
2. Run:

   ```bash
   cd "<repo>"
   CURATOR_MODE=dry python3 tools/telegram.py whoami
   ```

   It prints the chat ids that have messaged the bot (yours is the only one).
3. Put that id in `.env`:

   ```
   CURATOR_TELEGRAM_CHAT_ID=<your chat id>
   ```

Curator only reads messages from that chat id and only sends to it.

## 3. Check

```bash
CURATOR_MODE=dry python3 tools/telegram.py send --text "Curator is connected." --kind status
```

You should receive `[DRY RUN] Curator is connected.` on Telegram. Dry mode
sends for real but always adds the prefix, so you can tell test messages from
live ones.

## Commands you can send later

- `/rules` shows the current rules.
- `/status` lists upcoming bookings.
- Free text like "no more crypto talks" or "add a film screening every other week"
  changes the rules; Curator replies with exactly what changed, or asks if the
  request is ambiguous.
- Replies to rating prompts ("4, great speaker" or "didn't go") and to numbered questions.
