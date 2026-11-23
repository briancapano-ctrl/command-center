# Command Center

A live command center for Brian's personal accounts, built to stay open on a dedicated monitor all day. It runs on free GitHub Actions plus a small job on the Mac mini. No AI credits, no Perplexity Computer.

Cloud job (GitHub Actions, every 15 minutes): Gmail, Hotmail/Outlook, Google and Outlook calendars, YouTube, sports, trend history.
Mac job (launchd, every 10 minutes, pushes only when something changed, and at least hourly): iMessage and SMS unread counts, texts waiting on a reply, Apple Reminders, Apple Home status (read-only, through HomeBot). Encrypted before it leaves the Mac.
In the browser: the clock, weather and live scores update by themselves (scores every 30 seconds during a game), and the page re-checks for new data every 90 seconds without reloading.
Output: one page at `https://<your-github-name>.github.io/<repo>/`. All data inside is AES-256 encrypted and opens only with your passphrase. A phone alert with the top items arrives once a day after 6 AM Eastern through ntfy.

## Apple Home (v10, Nov 22, 2026)
- Home scene: a night illustration of the house (drawn from the builder's listing photo) with glowing markers for the upstairs thermostat, front door light, front door lock and door sensor, and the office shades. Five glass pills across the bottom: lights on, doors, lock, shades, inside temperatures. An "All secure" badge turns red and pulses when a door is open or the lock is unlocked.
- Beside it: Security (ring of checks, the lock with its battery, each door sensor, rooms with motion right now), Climate (a dial per thermostat with the set point, humidity and fan), Lights and shades (each light, shade positions, the Home scenes), Batteries and network (lowest battery first, then internet, uptime, backup, Mac disk).
- Elsewhere: a Secure or alert capsule in the status bar, a Home line in the Daily brief and the Dynamic Island, and the overview Home tiles now lead with the lock, doors, lights and inside temperature. Open doors, an unlocked lock, a safety alarm or a battery at 20% or less also become Needs you items.
- Scene buttons (added Nov 22, 2026 at Brian's request): Good Morning and Good Night sit under the house name. Tap once to arm ("Tap again to run"), tap again within 4 seconds to run. The button shows Running, then the scene ran or the reason it did not. The page signs the request with a key derived from the passphrase and sends it through a private ntfy topic that only the encrypted page knows. A small listener on the Mac mini (`mac/home_listener.py`, launchd agent `com.commandcenter.homectl`, installed and kept running by the Mac job) accepts only signed requests less than 2 minutes old, never the same one twice, and only those two scene names; it runs HomeBot's `trigger-scene` and sends back a signed answer, then refreshes the dashboard. The buttons appear only while the listener has checked in within 15 minutes. Nothing else on the page can control the house.
- Room names on the page are the Apple Home room names exactly as set in the Home app. The two Office shades are drawn on the two front-left porch windows (left and right).
- Status is otherwise read-only. The Mac job calls HomeBot for HomeKit's command-line reader (`get-home-items`; the scene listener is the only place `run-home-action` is used, for those two scenes) with the automation token kept in `~/.config/command-center/env`. HomeBot cannot export everything in one go on this home, so the job reads one device type at a time, then one room at a time, then the plain-text listing for anything left. The raw reading stays on the Mac (`~/CommandCenter/home/homebot.json`, owner-only); only names, rooms and states, with no device identifiers, go into the encrypted snapshot. Temperatures arrive in Celsius and are shown in Fahrenheit.
- The house picture is encrypted with the same passphrase (`docs/art/house.enc`) and decrypted in the browser, so the public repository does not show the house.
- HomeBot has no lock-state field, so a lock it reports as active is shown as locked (HomeKit's secured state). Cameras and the doorbell are not exposed by HomeBot and do not appear.

## Look (v9 Glass, Nov 22, 2026)
- Apple-style wall display: frosted-glass widgets over a vivid glass-ribbon wallpaper that changes with the day. Morning peach (sunrise to 11 AM), daytime blue, evening amber (the hour before sunset through dusk), night navy. The wallpapers crossfade; they never move, so the glass stays cheap to draw.
- Status bar: Capano Home and the current scene on the left (plus the time on every scene except Overview), a black Dynamic Island in the middle, and glass status capsules on the right (internet ping, texts, Gmail, Hotmail, outside temperature).
- Dynamic Island rotates one update every 7 seconds: the next or live game, the next event within 12 hours, the nearest birthday or holiday, overdue reminders, the weather. During a game it alternates the live score (red ring) with everything else. Click it to open that scene or list.
- Overview on a 12-column grid. Top row, four equal widgets: a lock-screen clock (date, big time, the greeting as the page title, the daily line); the On this day photo with its date ("November 22, 2018"); an Apple Weather-style widget (big temperature, condition, high and low, rain chance, six hours, three days with range bars, and moving rain, snow, clouds, sun glow, stars or lightning behind it); the game in team colors like a Live Activity, with the other teams below. Second row: Needs you, Up next and Work, Family, Daily brief. Bottom row: six Home tiles (internet, uptime over 24 hours, Mac mini, disk free, backup, Hotmail storage; amber when something needs a look) and a Sun and moon card.
- Siri-style rainbow edge glow: sweeps once when the page opens, breathes during a live Eagles, Flyers or Phillies game and on a birthday.
- Icon rail is a glass capsule of icons (names show on hover). Portrait wall: 2 x 2 widgets, Home tiles across the bottom, the rail as a dock. Phone: one column.
- Lock screen shows the date and time over the wallpaper with a glass passphrase panel.
- Type uses the Mac's San Francisco fonts (Inter on other computers). Look button or L key still switches to Bright; Glass is the default, including in Plash.

## Look (v8 Hub, Nov 22, 2026)
- Modeled on the smart-home hub screens you sent: a deep green frame, a left icon rail for the 11 scenes (the active one glows amber, with a thin bar showing time until the next auto scene), and warm cream cards.
- Header bar over a Carolina pines-and-lake panorama that follows the sun: day, golden hour, night. Brand, greeting with the daily line, status chips (internet ping, texts, Gmail, Hotmail, outside temperature; the mail and text chips open their drawers), clock and date.
- Overview, four columns: a full-bleed On this day photo (or the print on the wall when there are no photos) over Needs you; Home health gauges (uptime, internet, Mac disk free, Hotmail storage, plus backup and Mac uptime) over Today and next and Work; a weather card with a temperature arc between today's low and high, rain chance, sunrise and sunset and the next three days over Family (countdowns and Reconnect); a Game day card in the team's colors (live score and win chance during a game, otherwise the next game with TV) with the other teams below, over the Daily brief.
- Daily brief is plain status checks computed in the page (no AI): data sources fresh, weather alerts, overdue reminders, today's game or final, nearest birthday, texts waiting, backup, Hotmail storage, days left in the year.
- Photo, health, weather and game cards open their scenes when clicked.
- Look button (or L key) switches to Bright: the v7 light wall with white cards. Saved per browser; Hub is the default, including in Plash.
- Portrait wall: 2 x 2 columns with the rail as a dock along the bottom. Phone: rail scrolls across the top, one column.
- The colored counter tiles and the header weather tile are retired; their numbers moved to the header chips and the weather card.

## Look (v7, Nov 22, 2026)
- Bright around the clock: a sunlit wall tinted by the season (three soft color glows that shift toward indigo at night), white cards, bold Cabinet Grotesk and Satoshi type. The dark night room and night dimming are retired.
- Every area has its own color and icon: Needs you rose, Today orange, Work blue, Home green, Teams teal, Family pink, News by section, Inbox in each service's color.
- The five counters are solid color tiles; the next-game tile wears the team's color.
- Weather is a tile in the header (sky color follows the conditions and the night). The window illustration and the framed print left the header; the print still hangs in the Almanac scene.
- Sports cards carry the team color across the top with large logos; Family shows faces (initials) for Reconnect, Most texted and Birthdays.
- Garland only for celebrations: team pennants on game day, a banner on birthdays. Falling leaves and snow are off; birthday confetti stays.
- On the wall, the overview puts Home under Needs you so Today and next has room, and shows On this day photos in place of the print.

## What you see (v6, Nov 22, 2026)
- Your world ticker: a slow crawl along the bottom with live scores, today's games and TV channel, last results, birthdays and holidays coming up, the year-end countdown, and the top headlines. Hover to pause. It says "Game on" in red while a Philly team is playing.
- News scene: Philly sports (Eagles, Flyers, Phillies stories from ESPN and the Inquirer, tagged by team), Hotel world (Hotel Dive, Skift, hotel technology news, with any Allbridge mention pinned first), Close to home (WRAL, ABC11), Nation and world (NPR, Google News), AI and tech (The Verge). Headlines refresh at most every 45 minutes. Click any one to open the story.
- Family scene: countdowns to birthdays, holidays and family calendar events (with any Philly game that day), texts waiting on you, people you text often but have not in three weeks (Reconnect), who you texted most this week, and On this day photos. Names and counts only; message text never leaves the Mac.
- Sports scene: record, last result, TV and venue, the next games and two team headlines per team. During a game: score, down and distance, a win-chance bar and the last play, updated every 30 seconds.
- Weather alerts from the National Weather Service show as a red banner when one is active for home.
- New designs apply themselves overnight (2 to 5 AM) or while the tab is in the background. During the day a small "New version ready" button appears in the status line instead, so nothing reloads in front of you.

## As your Mac desktop wallpaper (Plash)
1. Install Plash, free, from the Mac App Store (by Sindre Sorhus).
2. Plash menu bar icon > Add Website > `https://briancapano-ctrl.github.io/command-center/#wall`.
3. Turn on Browsing Mode once, unlock with the passphrase (leave Remember checked), then turn Browsing Mode off.
4. Plash Settings > Display: pick the screen. The page detects Plash, goes to wall mode, and hides the buttons and the Work card (work data stays in Chrome).
5. Leave Plash's reload interval off. The page refreshes its own data every 90 seconds.

## Wall display (the always-on monitor)
1. On the monitor's computer open the Pages URL with `#wall` on the end, unlock once, leave "Remember on this device" checked.
2. Press F for full screen and click Keep awake so the screen never sleeps. Hide the mouse and the buttons fade out.
3. Wall mode is one screen with no scrolling. Rows that do not fit are dropped from the bottom instead of being cut in half.
4. It picks its layout from the monitor: three columns on a landscape screen, one tall stack on a portrait screen. Nothing to set.
5. It stays bright day and night (v7), and the layout drifts a few pixels over time to prevent burn-in.
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
