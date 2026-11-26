from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.sessions.models import Session
from django.test import Client, TestCase, override_settings
from django.utils import timezone


ORIGIN = "http://localhost:8080"


@override_settings(UI_ORIGIN=ORIGIN, CORS_ALLOWED_ORIGINS=[ORIGIN])
class BrowserAuthTests(TestCase):
    def setUp(self):
        get_user_model().objects.create_user(username="browser-user", password="test-password")
        self.client = Client(enforce_csrf_checks=True)

    def sign_in(self, origin=ORIGIN):
        return self.client.post(
            "/api/session/",
            {"username": "browser-user", "password": "test-password"},
            content_type="application/json",
            headers={"Origin": origin},
        )

    def test_allowed_browser_session_can_log_out_without_a_cookie(self):
        result = self.sign_in()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.headers["Access-Control-Allow-Origin"], ORIGIN)
        headers = {"Authorization": "Bearer " + result.json()["token"], "Origin": ORIGIN}
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/parents/live/", headers=headers).status_code, 200)
        self.assertEqual(self.client.post("/accounts/logout/", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/parents/live/", headers=headers).status_code, 401)

    def test_expired_browser_session_and_cookie_session_are_rejected_as_bearer_tokens(self):
        token = self.sign_in().json()["token"]
        Session.objects.filter(session_key=token).update(expire_date=timezone.now() - timedelta(seconds=1))
        self.client.cookies.clear()
        self.assertEqual(self.client.get("/parents/live/", headers={"Authorization": "Bearer " + token}).status_code, 401)

        self.client.force_login(get_user_model().objects.get(username="browser-user"))
        cookie_token = self.client.cookies["trip_ops_sessionid"].value
        self.assertEqual(self.client.post("/accounts/logout/").status_code, 403)
        self.assertEqual(
            self.client.post("/accounts/logout/", headers={"Authorization": "Bearer " + cookie_token}).status_code,
            401,
        )

    def test_unlisted_browser_origin_cannot_log_in(self):
        response = self.sign_in(origin="https://unlisted.example")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)
