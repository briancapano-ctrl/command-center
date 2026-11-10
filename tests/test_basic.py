import json, os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cc import render, priorities
from cc.demo import sample


class T(unittest.TestCase):
    def test_roundtrip(self):
        blob = render.encrypt({"a": 1}, "pw")
        self.assertEqual(render.decrypt(blob, "pw"), {"a": 1})
        with self.assertRaises(Exception):
            render.decrypt(blob, "wrong")

    def test_model(self):
        m = priorities.build(sample(), {})
        self.assertTrue(any("Simon" in t["t"] for t in m["tasks"]))
        self.assertTrue(m["kpis"])

    def test_empty_sources_do_not_crash(self):
        m = priorities.build({"errors": {"gmail": "boom"}}, {})
        self.assertIn("gmail", m["errors"])

class CollectNoCredentials(unittest.TestCase):
    def test_collect_runs_without_any_secrets(self):
        import os
        from cc import build
        old = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith(("GOOGLE_", "MS_"))}
        try:
            build.sports.collect = lambda: []          # no network in tests
            src = build.collect({}, "pw")
            self.assertIn("errors", src)
        finally:
            os.environ.update(old)


if __name__ == "__main__":
    unittest.main()


def test_delete_approved_only_unread_listed_and_not_protected(monkeypatch):
    from cc import ms_graph as M
    msgs = [
        {"id": "a", "isRead": False, "from": {"emailAddress": {"address": "x@uber.com"}}, "receivedDateTime": "2026-01-03T00:00:00Z"},
        {"id": "b", "isRead": True, "from": {"emailAddress": {"address": "x@uber.com"}}, "receivedDateTime": "2026-01-02T00:00:00Z"},
        {"id": "c", "isRead": False, "from": {"emailAddress": {"address": "x@robinhood.com"}}, "receivedDateTime": "2026-01-01T00:00:00Z"},
        {"id": "d", "isRead": False, "from": {"emailAddress": {"address": "x@email.dailywire.com"}}, "receivedDateTime": "2025-12-31T00:00:00Z"},
        {"id": "e", "isRead": False, "from": {"emailAddress": {"address": "mom@gmail.com"}}, "receivedDateTime": "2025-12-30T00:00:00Z"},
    ]
    sent = []
    monkeypatch.setattr(M, "_g", lambda tok, path: {"value": msgs})
    monkeypatch.setattr(M, "http", lambda method, url, headers=None, body=None, form=None, timeout=30: sent.append(body) or {})
    done, nxt = M.delete_approved("t", "2026-02-01T00:00:00Z", 5)
    ids = [r["url"].split("/")[3] for b in sent for r in b["requests"]]
    assert sorted(ids) == ["a", "d"]
    assert done == {"uber.com": 1, "email.dailywire.com": 1}
    assert nxt is None
