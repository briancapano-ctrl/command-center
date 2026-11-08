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
