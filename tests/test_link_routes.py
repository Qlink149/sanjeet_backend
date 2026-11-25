"""Unit tests for the /dashboard/links endpoints (DB layer mocked)."""

import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from qlink_chatbot.routes.link_routes import link_router, register_auth_handler
from qlink_chatbot.utils.auth_token import issue_token

GROUP = "https://chat.whatsapp.com/LsQjGBZ74fP2tDB1TWmQ5V"
M = "qlink_chatbot.routes.link_routes."


def _row(slug="coterie", target=GROUP, note="", clicks=3):
    return {"slug": slug, "target": target, "note": note, "clicks": clicks}


class LinkRoutesTest(unittest.TestCase):
    def setUp(self):
        env = patch.dict("os.environ", {"DASHBOARD_TOKEN_SECRET": "test-secret"})
        env.start()
        self.addCleanup(env.stop)
        app = FastAPI()
        app.include_router(link_router, prefix="/dashboard")
        register_auth_handler(app)
        token, _ = issue_token("admin")
        self.client = TestClient(app, headers={"Authorization": f"Bearer {token}"})
        self.anon = TestClient(app)

    @patch(M + "list_short_links")
    def test_list_includes_public_url(self, lst):
        lst.return_value = [_row()]
        res = self.client.get("/dashboard/links")
        self.assertEqual(res.status_code, 200)
        item = res.json()["data"][0]
        self.assertEqual(
            item["public_url"], "https://sanjeet.ray.claraai.tech/go/coterie"
        )
        self.assertEqual(item["clicks"], 3)

    @patch.dict("os.environ", {"DASHBOARD_PUBLIC_URL": "https://example.test/"})
    @patch(M + "list_short_links")
    def test_public_url_configurable(self, lst):
        lst.return_value = [_row()]
        item = self.client.get("/dashboard/links").json()["data"][0]
        self.assertEqual(item["public_url"], "https://example.test/go/coterie")

    @patch(M + "upsert_short_link")
    @patch(M + "get_short_link")
    def test_create_success(self, get, upsert):
        get.side_effect = [None, _row()]
        res = self.client.post(
            "/dashboard/links", json={"slug": "Coterie", "target": GROUP}
        )
        self.assertEqual(res.status_code, 201)
        upsert.assert_called_once_with("coterie", GROUP, "")

    def test_create_validation_errors(self):
        for body in (
            {"slug": "bad slug", "target": GROUP},
            {"slug": "ok", "target": "http://insecure.com"},
            {"slug": "ok", "target": "javascript:alert(1)"},
        ):
            res = self.client.post("/dashboard/links", json=body)
            self.assertEqual(res.status_code, 400, body)
            self.assertFalse(res.json()["success"])

    @patch(M + "upsert_short_link")
    @patch(M + "get_short_link")
    def test_create_duplicate_409(self, get, upsert):
        get.return_value = _row()
        res = self.client.post(
            "/dashboard/links", json={"slug": "coterie", "target": GROUP}
        )
        self.assertEqual(res.status_code, 409)
        upsert.assert_not_called()

    @patch(M + "upsert_short_link")
    @patch(M + "get_short_link")
    def test_update_success_keeps_other_fields(self, get, upsert):
        get.return_value = _row(note="old")
        new = "https://chat.whatsapp.com/NEW"
        res = self.client.patch("/dashboard/links/coterie", json={"target": new})
        self.assertEqual(res.status_code, 200)
        upsert.assert_called_once_with("coterie", new, "old")

    @patch(M + "get_short_link")
    def test_update_not_found(self, get):
        get.return_value = None
        res = self.client.patch("/dashboard/links/nope", json={"note": "x"})
        self.assertEqual(res.status_code, 404)

    def test_update_invalid_target(self):
        res = self.client.patch("/dashboard/links/coterie", json={"target": "ftp://x"})
        self.assertEqual(res.status_code, 400)

    @patch(M + "delete_short_link")
    def test_delete(self, delete):
        delete.return_value = True
        self.assertEqual(self.client.delete("/dashboard/links/coterie").status_code, 200)
        delete.return_value = False
        self.assertEqual(self.client.delete("/dashboard/links/coterie").status_code, 404)

    def test_requires_valid_token(self):
        calls = [
            ("get", "/dashboard/links", None),
            ("post", "/dashboard/links", {"slug": "a", "target": GROUP}),
            ("patch", "/dashboard/links/a", {"note": "x"}),
            ("delete", "/dashboard/links/a", None),
        ]
        bad_headers = [
            {},
            {"Authorization": "Bearer garbage"},
            {"Authorization": "Basic abc"},
            {"Authorization": "Bearer "},
        ]
        with patch(M + "list_short_links", return_value=[]) as lst:
            for method, url, body in calls:
                for h in bad_headers:
                    res = getattr(self.anon, method)(url, headers=h, **({"json": body} if body else {}))
                    self.assertEqual(res.status_code, 401, (method, h))
                    self.assertEqual(
                        res.json(), {"success": False, "message": "Unauthorized"}
                    )
            lst.assert_not_called()
            self.assertEqual(self.client.get("/dashboard/links").status_code, 200)

    def test_expired_token_rejected(self):
        old, _ = issue_token("admin", now=1000)
        res = self.anon.get("/dashboard/links", headers={"Authorization": f"Bearer {old}"})
        self.assertEqual(res.status_code, 401)


if __name__ == "__main__":
    unittest.main()
