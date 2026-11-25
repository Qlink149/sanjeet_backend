"""Tests for dashboard tokens, /login token field, and CORS for Authorization."""

import json
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient

from qlink_chatbot.routes import dashboard_routes
from qlink_chatbot.utils import auth_token as at

SECRET = {"DASHBOARD_TOKEN_SECRET": "s1"}


class TokenTest(unittest.TestCase):
    def test_round_trip(self):
        with patch.dict("os.environ", SECRET):
            tok, exp = at.issue_token("admin", now=1000)
            self.assertEqual(exp, 1000 + 12 * 3600)
            p = at.verify_token(tok, now=1001)
            self.assertEqual((p["sub"], p["iat"], p["exp"]), ("admin", 1000, exp))

    def test_expired(self):
        with patch.dict("os.environ", SECRET):
            tok, exp = at.issue_token("admin", now=1000)
            with self.assertRaises(at.TokenError):
                at.verify_token(tok, now=exp)

    def test_tampered_signature_and_payload(self):
        with patch.dict("os.environ", SECRET):
            tok, _ = at.issue_token("admin", now=1000)
            body, sig = tok.split(".")
            flipped = ("A" if sig[0] != "A" else "B") + sig[1:]
            with self.assertRaises(at.TokenError):
                at.verify_token(f"{body}.{flipped}", now=1001)
            forged = at._b64(
                json.dumps({"sub": "admin", "iat": 1000, "exp": 10**12}).encode()
            )
            with self.assertRaises(at.TokenError):
                at.verify_token(f"{forged}.{sig}", now=1001)

    def test_wrong_secret(self):
        with patch.dict("os.environ", SECRET):
            tok, _ = at.issue_token("admin", now=1000)
        with patch.dict("os.environ", {"DASHBOARD_TOKEN_SECRET": "other"}):
            with self.assertRaises(at.TokenError):
                at.verify_token(tok, now=1001)

    def test_fails_closed_without_secret(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(at.TokenError):
                at.issue_token("admin")
            with self.assertRaises(at.TokenError):
                at.verify_token("a.b")

    def test_derived_secret_from_existing_env(self):
        with patch.dict("os.environ", {"LOGIN_PASS": "pw"}, clear=True):
            tok, _ = at.issue_token("admin", now=1000)
            self.assertEqual(at.verify_token(tok, now=1001)["sub"], "admin")
        with patch.dict("os.environ", {"LOGIN_PASS": "pw2"}, clear=True):
            with self.assertRaises(at.TokenError):
                at.verify_token(tok, now=1001)

    def test_garbage(self):
        with patch.dict("os.environ", SECRET):
            for bad in (None, "", "x", "a.b", "a.b.c", ".", "!!!.???", 123):
                with self.assertRaises(at.TokenError, msg=repr(bad)):
                    at.verify_token(bad)


class LoginTest(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(dashboard_routes.dashboard_router, prefix="/dashboard")
        self.client = TestClient(app)

    def _login(self, u, p):
        with patch.object(dashboard_routes, "us", "admin"), patch.object(
            dashboard_routes, "pwd", "pw"
        ), patch.dict("os.environ", SECRET):
            return self.client.post("/dashboard/login", json={"username": u, "password": p})

    def test_success_keeps_old_fields_and_adds_token(self):
        res = self._login("admin", "pw")
        self.assertEqual(res.status_code, 201)
        body = res.json()
        self.assertTrue(body["success"])
        self.assertIn("expires_at", body)
        with patch.dict("os.environ", SECRET):
            self.assertEqual(at.verify_token(body["token"])["sub"], "admin")

    def test_failures_unchanged(self):
        res = self._login("admin", "nope")
        self.assertEqual(res.status_code, 402)
        self.assertEqual(
            res.json(), {"success": False, "message": "Invalid Username or Password"}
        )
        self.assertEqual(self._login("", "pw").status_code, 401)


class CorsTest(unittest.TestCase):
    def test_preflight_allows_authorization_header(self):
        app = FastAPI()
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        res = TestClient(app).options(
            "/x",
            headers={
                "Origin": "https://dash.example",
                "Access-Control-Request-Method": "PATCH",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("authorization", res.headers["access-control-allow-headers"].lower())


if __name__ == "__main__":
    unittest.main()
