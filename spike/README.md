# Phase 0 — Telegram Business Mode Spike

Goal: prove that the bot receives `business_connection` and `business_message`
updates and can reply on behalf of the connected Premium account.

If this works end-to-end, we proceed to Phase 1. If it doesn't, we re-evaluate
the project before writing production code.

---

## Prerequisites

You need:

1. A Telegram **Premium** account (the "tutor" account in our scenario).
2. Optionally a second Telegram account ("student") to test client → tutor messages.
3. A bot created in [@BotFather](https://t.me/BotFather) — see steps below.

---

## Step 1. Create a bot in @BotFather

Open `@BotFather` and run:

```
/newbot
→ Bot name: TutorBot Spike
→ Bot username: <something>_spike_bot   (must end with `bot`)
```

BotFather replies with an HTTP API token like `123456:ABC...`. Save it — you'll
paste it into `.env` in step 3.

## Step 2. Enable Business Mode for the bot

Still in `@BotFather`:

```
/mybots
→ select your bot
→ Bot Settings
→ Business Mode
→ Turn On
```

Then in the same `Business Mode` menu open **Manage permissions** and at minimum
allow:

- ✅ Read messages
- ✅ Reply to messages
- ✅ Manage messages

This is required for `business_message` updates to be delivered.

## Step 3. Configure local env

```bash
cd /home/ser/my_projects/tutor_automation
cp .env.example .env
# paste the bot token into TELEGRAM_BOT_TOKEN
```

## Step 4. Start the spike bot

```bash
uv run python -m spike.bot
```

You should see:

```
Spike bot @<username>_spike_bot (id=...) starting via long-polling.
Allowed updates: ['message', ..., 'business_connection', 'business_message', ...]
```

Send `/start` to the bot in a direct chat from your tutor account — it should
reply confirming it's alive.

## Step 5. Connect the bot to your Premium account

On your tutor's Premium-enabled Telegram client:

```
Settings (⚙️)
→ Telegram Business
→ Chatbots
→ Bot Username: @<username>_spike_bot
→ Access: All Chats   (or "Excluding" / "Selected", anything that includes the
                       chat you'll test with)
→ Permissions: ✅ Reply to Messages
              ✅ Manage Messages
              ✅ Read Messages
→ Save
```

In the spike's terminal you should immediately see:

```
business_connection: id=<connection_id> user_id=<your tutor id> ...
                     is_enabled=True can_reply=True
```

If you see this — **Business Mode is wired up**.

## Step 6. Test on a real chat

From a SECOND Telegram account (the "student"), open a chat with your tutor's
account and send any text message, e.g. `привет, можно перенести среду на
пятницу?`.

In the spike's terminal you should see:

```
business_message: chat_id=... from_user=<student id> connection_id=...
                  text='привет, можно перенести...'
```

The student should receive a reply from your tutor's account:

```
[spike] received: привет, можно перенести среду на пятницу?
```

The student does NOT see "from a bot" — Telegram routes the bot's reply through
the tutor's account.

If this works → **Phase 0 done**. We have proof of concept.

---

## What we explicitly want to verify in this spike

- [ ] `business_connection` update arrives when tutor enables the bot in Settings
- [ ] `business_message` update arrives when a student writes the tutor
- [ ] Bot can reply via `business_connection_id` and the student sees the
      message as if from the tutor
- [ ] 24-hour activity window: send a student message, wait >24h with no chat
      activity, see if the bot can still send. (Documented behaviour: it can't.)
- [ ] What happens when the **tutor manually replies** in the same chat — does
      the bot see the outbound message? (Needed for `handoff_detector`.)

After verification we delete `spike/` and move to Phase 1.
