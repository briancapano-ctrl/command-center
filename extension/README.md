# Work Lane add-on (Comet or Chrome)

Shows three work numbers on the Command Center without sending anything anywhere:
unread count for the folders you pick, your next meeting time today, and the red / orange / yellow counts from your latest Copilot briefing.

## What leaves your work pages, exactly
- A number per folder you list, plus your own label for it (default: `Inbox unread`).
- Meeting start and end times. No titles, no attendees.
- From the Copilot briefing: three counts and the briefing's own date line (for example "Friday, November 6 | 7:24 PM ET").
- Nothing else. No sender names, subjects, message text, customer names or links.

## Where it goes
- Into this browser's extension storage, then to the Command Center page open in the same browser window, through a page message. It is never uploaded, never written to the GitHub repo, never saved by the page.
- The add-on makes no network requests and asks for no host access beyond the pages listed in `manifest.json`.
- Nothing travels the other way. The add-on does not read your Command Center data and never types into Outlook, Teams or Copilot, so Copilot cannot see anything personal.

## Install (about 3 minutes)
1. Open the browser's extensions page (`chrome://extensions`, or `comet://extensions` in Comet). Turn on Developer mode.
2. Load unpacked, choose this `extension` folder.
3. Click the add-on icon. Edit the folder list if you want more than Inbox (format: `Folder name=Label shown`, one per line), then Save.
4. Click "Open and pin my work tabs". Sign in to Microsoft in each tab if asked.
5. Open your Command Center page in a tab of the same browser. The Work card turns live within about a minute.
Keep the three pinned tabs open. Only these pinned tabs ever reload or navigate themselves. Your other Outlook and Copilot tabs are only read.

## How it behaves
- It refreshes every 30 seconds. If a number is older than 25 minutes (1 hour for the briefing), the card says "sign in needed" instead of showing a stale number.
- The Copilot tab reopens the chat list every 15 minutes and opens your newest chat whose title contains "briefing" or "digest".
- The calendar tab returns to today's day view hourly and after midnight.
- If Microsoft changes its page layout, a number can show wrong or go blank. Tell me and I will fix the selector.

## Check with IT first
This is a locally loaded add-on in a browser that holds your Allbridge sign-in. If Allbridge manages that browser or restricts extensions, use a personal browser profile or skip it.
