"""Fake data so the page can be previewed without any accounts."""
from .util import now
import datetime as dt, random


def sample():
    n = now()
    at = lambda d, h, m=0: (n + dt.timedelta(days=d)).replace(hour=h, minute=m, second=0, microsecond=0)
    rnd = random.Random(7)
    hist = lambda start, step, k: [max(0, int(start + i * step + rnd.randint(-k, k))) for i in range(48)]
    game = lambda nm, d, h, m=0: {"name": nm, "when": at(d, h, m).isoformat(), "state": "pre", "detail": "", "score": {}}
    return {
        "errors": {},
        "mac": {"unread_total": 6, "unread_chats": 3, "as_of": "Updated 6:05 AM", "as_of_iso": (n - dt.timedelta(minutes=14)).isoformat(),
                "reminders": [{"title": "Call Simon Gill", "due": at(-12, 18).isoformat()}, {"title": "Schedule Starlink installation", "due": at(0, 12).isoformat()}],
                "waiting": [{"label": "Family group", "ago": "4h"}]},
        "gmail": {"unread_estimate": 128, "cleared": 87, "cats": {"inbox": 128, "primary": 31, "updates": 64, "promotions": 22, "social": 11, "forums": 0}, "recent": [
            {"from": "GitHub <noreply@github.com>", "domain": "github.com", "subject": "Run failed", "date": n.isoformat()},
            {"from": "Google <no-reply@accounts.google.com>", "domain": "google.com", "subject": "Security alert", "date": n.isoformat()},
            {"from": "Google <no-reply@accounts.google.com>", "domain": "google.com", "subject": "Security alert 2", "date": n.isoformat()},
            {"from": "LinkedIn <a@linkedin.com>", "domain": "linkedin.com", "subject": "x", "date": n.isoformat()},
            {"from": "YouTube <noreply-purchases@youtube.com>", "domain": "youtube.com", "subject": "Update required: your Premium payment method", "date": n.isoformat()}]},
        "outlook_folders": [{"name": "Inbox", "unread": 43661, "total": 60648}, {"name": "Archive", "unread": 3179, "total": 3436}, {"name": "Junk Email", "unread": 922, "total": 936}, {"name": "Clutter", "unread": 140, "total": 800}], "outlook_swept": 12, "outlook_unread": [],
        "gcal": [{"title": "Dentist", "start": at(0, 15).isoformat(), "all_day": False, "cal": "Google"},
                 {"title": "Youth baseball practice", "start": at(0, 18, 30).isoformat(), "all_day": False, "cal": "Google"},
                 {"title": "Jon's birthday", "start": at(2, 0).strftime("%Y-%m-%d"), "all_day": True, "cal": "Birthdays"},
                 {"title": "Call with contractor", "start": at(1, 10).isoformat(), "all_day": False, "cal": "Google"}],
        "outlook_cal": [{"title": "Team dinner", "start": at(3, 19).isoformat(), "all_day": False, "cal": "Outlook"}],
        "youtube": {"handle": "@briancapano", "subs": 0, "videos": 0, "views_total": 6, "views_30d": 0},
        "sports": [
            {"team": "Eagles", "path": "football/nfl", "abbr": "PHI", "live": [], "next": [game("PIT @ PHI", 14, 16, 25)], "last": [{"name": "NYG @ PHI", "score": {"PHI": "11", "NYG": "19"}}]},
            {"team": "Flyers", "path": "hockey/nhl", "abbr": "PHI", "live": [], "next": [game("EDM @ PHI", 7, 19, 30)], "last": [{"name": "PHI @ NYR", "score": {"NYR": "3", "PHI": "2"}}]},
            {"team": "Phillies", "path": "baseball/mlb", "abbr": "PHI", "live": [], "next": [], "last": [{"name": "PHI @ ATL", "score": {"ATL": "6", "PHI": "2"}}]},
        ],
        "_history": {"texts": hist(12, -.2, 6), "gmail": hist(140, -.4, 14), "hotmail": hist(44800, -22, 40), "need": hist(3, 0, 1)},
    }
