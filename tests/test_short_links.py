"""Unit tests for the /go/<slug> redirect links."""

import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from qlink_chatbot.database import short_links as sl
from qlink_chatbot.routes.short_link_routes import short_link_router

GROUP = "https://chat.whatsapp.com/LsQjGBZ74fP2tDB1TWmQ5V"


class ValidationTest(unittest.TestCase):
    def test_slug_rules(self):
        self.assertEqual(sl.normalize_slug(" Coterie "), "coterie")
        for bad in ("", "a b", "../x", "x" * 41, "-x", "a/b"):
            with self.assertRaises(ValueError):
                sl.normalize_slug(bad)

    def test_target_rules(self):
        self.assertEqual(sl.validate_target(GROUP), GROUP)
        self.assertEqual(sl.validate_target("@masterclass"), "@masterclass")
        for bad in ("http://x.com", "javascript:alert(1)", "//evil.com", "", "x.com"):
            with self.assertRaises(ValueError):
                sl.validate_target(bad)


@patch("qlink_chatbot.routes.short_link_routes.record_click")
@patch("qlink_chatbot.routes.short_link_routes.get_short_link")
class RouteTest(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(short_link_router)
        self.client = TestClient(app, follow_redirects=False)

    def test_redirects_to_target(self, get_link, record):
        get_link.return_value = {"slug": "coterie", "target": GROUP}
        res = self.client.get("/go/coterie")
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers["location"], GROUP)
        record.assert_called_once_with("coterie")

    def test_unknown_slug_404(self, get_link, record):
        get_link.return_value = None
        self.assertEqual(self.client.get("/go/nope").status_code, 404)
        record.assert_not_called()

    def test_click_failure_does_not_block_redirect(self, get_link, record):
        get_link.return_value = {"slug": "coterie", "target": GROUP}
        record.side_effect = RuntimeError("db down")
        self.assertEqual(self.client.get("/go/coterie").status_code, 302)

    @patch("qlink_chatbot.routes.short_link_routes.get_active_masterclass")
    def test_masterclass_resolves_active_link(self, active, get_link, record):
        get_link.return_value = {"slug": "masterclass", "target": "@masterclass"}
        active.return_value = {"meeting_url": "https://meet.example.com/abc"}
        res = self.client.get("/go/masterclass")
        self.assertEqual(res.status_code, 302)
        self.assertEqual(res.headers["location"], "https://meet.example.com/abc")

    @patch("qlink_chatbot.routes.short_link_routes.get_active_masterclass")
    def test_masterclass_not_live_is_404(self, active, get_link, record):
        get_link.return_value = {"slug": "masterclass", "target": "@masterclass"}
        active.return_value = None
        self.assertEqual(self.client.get("/go/masterclass").status_code, 404)


if __name__ == "__main__":
    unittest.main()
