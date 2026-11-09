# Work Lane add-on (Comet or Chrome)

Shows your actual work agenda and briefing priorities in a dedicated Work view.
The source tabs send data one way to this browser's Command Center page. No AI calls or Computer runs are needed.

## What leaves your work pages, exactly
- A number per folder you list, plus your own label for it (default: `Inbox unread`).
- Calendar: appointment titles, start/end, all-day status and location from the selected Allbridge work calendar. Private appointment details are redacted. No attendees or meeting bodies.
- Copilot: priority headings, short extracted context and next-action passages, priority counts, the briefing's own date line and a link to the original chat.
- No email subjects, bodies, sender names or attachments. No data travels back from the dashboard into work apps.

## Where it goes
- Into this browser's extension storage, then to the Command Center page open in the same browser window, through a page message. It is never uploaded, never written to the GitHub repo, never saved by the page.
- The add-on makes no network requests and asks for no host access beyond the pages listed in `manifest.json`.
- Nothing travels the other way. The add-on does not read your Command Center data and never types into Outlook, Teams or Copilot, so Copilot cannot see anything personal.

## Install (about 3 minutes)
1. Open the browser's extensions page (`chrome://extensions`, or `comet://extensions` in Comet). Turn on Developer mode.
2. Load unpacked, choose this `extension` folder.
3. Click the add-on icon. Edit the folder list if you want more than Inbox (format: `Folder name=Label shown`, one per line), then Save.
4. Click "Open and pin my work tabs". Sign in to Microsoft in each tab if asked.
5. Open your Command Center page in the same browser. Click Work in the scene navigation, or Open work view on Overview. In the work calendar tab, select only the Allbridge calendar. Mixed work/personal calendar selections are rejected.
Keep the three pinned tabs open. Only these pinned tabs ever reload or navigate themselves. Your other Outlook and Copilot tabs are only read.

## How it behaves
- The three work tabs report in to the add-on when they load, so it knows exactly which tabs are its own. A watchdog checks every 2 minutes and, if one of them stopped updating (Comet can put background tabs to sleep), reloads just that tab. After you reload or update the add-on, it refreshes its own tabs and the Command Center page by itself.
- It refreshes every 30 seconds. If a number is older than 25 minutes (1 hour for the briefing), the card says "sign in needed" instead of showing a stale number.
- The Copilot tab reopens the chat list every 15 minutes and opens your newest chat whose title contains "briefing" or "digest".
- The calendar tab returns to today's day view hourly and after midnight.
- If Microsoft changes its page layout, a number can show wrong or go blank. Tell me and I will fix the selector.

## Check with IT first
This is a locally loaded add-on in a browser that holds your Allbridge sign-in. If Allbridge manages that browser or restricts extensions, use a personal browser profile or skip it.
