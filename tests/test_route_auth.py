"""Pins which routes are public so a new route can never become public by accident."""

import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from qlink_chatbot.routes import dashboard_routes as dr
from qlink_chatbot.routes.link_routes import link_router
from qlink_chatbot.utils.auth_dependency import (
    register_auth_handler,
    require_dashboard_token,
)
from qlink_chatbot.utils.auth_token import issue_token

PUBLIC_DASHBOARD = {
    ("POST", "/dashboard/login"),
    ("GET", "/dashboard/ping"),
    ("GET", "/dashboard/cron/schedules"),
    ("GET", "/dashboard/cron/campaign-retries"),
    ("GET", "/dashboard/cron/masterclass-utility-reminders"),
    ("GET", "/dashboard/template-image/{template_id}"),
}
# Allowed to be public outside /dashboard (webhooks, public quiz site, redirects).
PUBLIC_OTHER_PREFIXES = ("/ping", "/gupshup/", "/quiz/", "/masterclass/", "/go/")
FRAMEWORK = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}


def _is_protected(route: APIRoute) -> bool:
    return any(
        d.call is require_dashboard_token for d in route.dependant.dependencies
    )


class RouteInventoryTest(unittest.TestCase):
    def test_public_routes_are_exactly_the_allow_list(self):
        from qlink_chatbot.main import app

        unexpected = []
        seen_public_dashboard = set()
        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue  # mounts (/static) are not API routes
            for method in route.methods - {"HEAD", "OPTIONS"}:
                key = (method, route.path)
                if route.path.startswith("/dashboard"):
                    if _is_protected(route):
                        continue
                    if key in PUBLIC_DASHBOARD:
                        seen_public_dashboard.add(key)
                    else:
                        unexpected.append(key)
                elif route.path in FRAMEWORK or route.path.startswith(
                    PUBLIC_OTHER_PREFIXES
                ):
                    continue
                else:
                    unexpected.append(key)
        self.assertEqual(
            unexpected,
            [],
            "Unexpected PUBLIC route(s) (no dashboard token). Put dashboard routes "
            "on the protected router, or add to the allow-list on purpose: "
            f"{unexpected}",
        )
        self.assertEqual(seen_public_dashboard, PUBLIC_DASHBOARD)


class ProtectedBehaviourTest(unittest.TestCase):
    def setUp(self):
        env = patch.dict(
            "os.environ", {"DASHBOARD_TOKEN_SECRET": "t", "CRON_SECRET": "cron"}
        )
        env.start()
        self.addCleanup(env.stop)
        app = FastAPI()
        app.include_router(dr.dashboard_router, prefix="/dashboard")
        app.include_router(dr.public_dashboard_router, prefix="/dashboard")
        app.include_router(link_router, prefix="/dashboard")
        register_auth_handler(app)
        self.client = TestClient(app)
        self.good = {"Authorization": f"Bearer {issue_token('a')[0]}"}

    def test_protected_route_token_matrix(self):
        url = "/dashboard/masterclasses"
        with patch.object(dr, "list_masterclasses", return_value=[]):
            for headers in (
                {},
                {"Authorization": "Bearer nope"},
                {"Authorization": f"Bearer {issue_token('a', now=1000)[0]}"},
            ):
                res = self.client.get(url, headers=headers)
                self.assertEqual(res.status_code, 401)
                self.assertEqual(
                    res.json(), {"success": False, "message": "Unauthorized"}
                )
            self.assertEqual(self.client.get(url, headers=self.good).status_code, 200)

    def test_other_protected_examples_reject_without_token(self):
        for method, url in (
            ("get", "/dashboard/chat/all"),
            ("get", "/dashboard/leads"),
            ("get", "/dashboard/campaigns"),
            ("get", "/dashboard/schedules"),
            ("post", "/dashboard/chat/send"),
            ("delete", "/dashboard/chat/template/x"),
        ):
            self.assertEqual(getattr(self.client, method)(url).status_code, 401, url)

    def test_allow_listed_routes_work_without_token(self):
        self.assertEqual(self.client.get("/dashboard/ping").status_code, 201)
        with patch.object(dr, "get_template_image", return_value=None):
            res = self.client.get("/dashboard/template-image/abc")
            self.assertNotEqual(res.status_code, 401)

    def test_cron_keeps_its_own_secret_check(self):
        res = self.client.get("/dashboard/cron/schedules")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["message"], "Unauthorized")
        with patch("qlink_chatbot.campaign_scheduler.run_due_schedules"):
            ok = self.client.get(
                "/dashboard/cron/schedules",
                headers={"Authorization": "Bearer cron"},
            )
        self.assertEqual(ok.status_code, 200)
        # A dashboard token is not a cron credential.
        bad = self.client.get("/dashboard/cron/schedules", headers=self.good)
        self.assertEqual(bad.status_code, 401)


if __name__ == "__main__":
    unittest.main()
