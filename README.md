# Command Center

A live command center for Brian's personal accounts, built to stay open on a dedicated monitor all day. It runs on free GitHub Actions plus a small job on the Mac mini. No AI credits, no Perplexity Computer.

Cloud job (GitHub Actions, every 15 minutes): Gmail, Hotmail/Outlook, Google and Outlook calendars, YouTube, sports, trend history.
Mac job (launchd, every 10 minutes, pushes only when something changed, and at least hourly): iMessage and SMS unread counts, texts waiting on a reply, Apple Reminders. Encrypted before it leaves the Mac.
In the browser: the clock, weather and live scores update by themselves (scores every 30 seconds during a game), and the page re-checks for new data every 90 seconds without reloading.
Output: one page at `https://<your-github-name>.github.io/<repo>/`. All data inside is AES-256 encrypted and opens only with your passphrase. A phone alert with the top items arrives once a day after 6 AM Eastern through ntfy.

## Wall display (the always-on monitor)
1. On the monitor's computer open the Pages URL with `#wall` on the end, unlock once, leave "Remember on this device" checked.
2. Press F for full screen and click Keep awake so the screen never sleeps. Hide the mouse and the buttons fade out.
3. Wall mode is one screen with no scrolling. Rows that do not fit are dropped from the bottom instead of being cut in half.
4. It picks its layout from the monitor: three columns on a landscape screen, one tall stack on a portrait screen. Nothing to set.
5. From 10 PM to 6 AM it dims, and the layout drifts a few pixels over time to prevent burn-in. Add `?dim=off` to the URL to disable dimming.
6. If data is more than 90 minutes old a red banner appears, so a dead job never goes unnoticed.
7. Keys: W wall/desk, F full screen. On a phone use Share > Add to Home Screen and it opens like an app.
Tip: a spare iPad, an old laptop or a Raspberry Pi with Chromium in kiosk mode works as the display. Use `chromium --kiosk "https://.../#wall"`.

## Work lane (optional)
A Work card shows your work Inbox unread count, next meeting time and the red/orange/yellow counts from your Copilot briefing. It uses a small browser add-on in `extension/`; work counts never touch GitHub or the cloud job, and nothing from this dashboard flows back to Outlook or Copilot. See `extension/README.md`.

## What it does on its own
- Gmail: archives and marks read promotions and social mail, labeled `Cleanup YYYY-MM-DD` for undo. Never deletes.
- Hotmail: marks read and archives unread inbox mail from the sender domains in `outlook_promo_domains`. Never deletes.
- Everything else is read-only.

## Not automated, by design
- Facebook, Instagram, WhatsApp, Meta AI, Horizon and X have no personal-account feed. They show numbers you type into `manual_channels` and say "Manual". Logging in with scripts risks locking the accounts.
- No AI-written reply drafts. A language model would need a paid key. The page lists who is waiting on you instead.

## Setup (about an hour once)
1. GitHub: create a public repo named `command-center`, upload this folder. Settings > Pages > Deploy from branch `main`, folder `/docs`.
2. Pick a long passphrase (five random words). It is the page password and the encryption key.
3. Google (Gmail, Calendar, YouTube): console.cloud.google.com > new project > enable Gmail API, Google Calendar API, YouTube Data API v3, YouTube Analytics API > OAuth consent screen, External, add yourself as a test user, then set Publishing status to In production (otherwise the token dies in 7 days) > Credentials > OAuth client ID, type Desktop app. Then on the Mac: `python3 setup/google_auth.py CLIENT_ID CLIENT_SECRET` and approve. It prints the refresh token.
4. Microsoft (Hotmail): either register your own app (portal.azure.com > Microsoft Entra ID > App registrations, personal accounts only, public client flows on, delegated Mail.ReadWrite and Calendars.Read) or use the device-code flow with `python3 setup/ms_auth.py CLIENT_ID`. Sign in only with the Hotmail account, never a work account. Save the printed refresh token as `MS_REFRESH_TOKEN`.
5. GitHub repo > Settings > Secrets and variables > Actions. Add: `CC_PASSPHRASE`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REFRESH_TOKEN`, `MS_CLIENT_ID`, `MS_REFRESH_TOKEN`, `CC_CONFIG` (paste your edited `config.example.json`), and `NTFY_TOPIC` (any long random string).
6. Phone: install the ntfy app, subscribe to that same topic.
7. Mac mini: add a deploy key (read/write) to this one repository and put the private half in `mac/deploy_key`. Run `bash mac/install.sh`, enter the dashboard passphrase, then add the printed Python path in System Settings > Privacy & Security > Full Disk Access. No GitHub token is stored on the Mac.
8. Actions tab > build > Run workflow. Open the Pages URL and unlock.

## Day to day
Nothing. Edit `manual_channels` in the `CC_CONFIG` secret when you want fresh social numbers.

## Limits to know
- The Mac must be on and awake. If it is not, the Mac card goes stale instead of guessing.
- GitHub pauses scheduled jobs in a public repo after 60 days with no commits. Every real data change is a commit, so this does not happen in normal use. If it ever does, press Run workflow once.
- Microsoft rotates its refresh token on every run. The job saves the new one encrypted in `state/ms.json`. If you ever reset the repo, redo step 4.
- A public repo with an encrypted page is safe only with a strong passphrase. Do not reuse one.
- Tests: `python3 -m unittest tests.test_basic`. Preview without accounts: `CC_PASSPHRASE=x python3 -m cc.build --demo`.
