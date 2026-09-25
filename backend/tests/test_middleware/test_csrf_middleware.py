"""ASGI-level checks for cookie write protection."""

import unittest

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.middleware.csrf import CSRFMiddleware


class TestCSRFMiddleware(unittest.TestCase):
    def setUp(self):
        self.writes = 0

        async def write(_request):
            self.writes += 1
            return JSONResponse({"saved": True})

        app = Starlette(routes=[Route("/change", write, methods=["POST"])])
        app.add_middleware(CSRFMiddleware, allowed_origins=["https://argus.example"])
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    def test_cross_site_form_with_cookie_is_rejected_before_write(self):
        response = self.client.post(
            "/change",
            data={"enabled": "false"},
            cookies={"access_token": "session"},
            headers={"Origin": "https://evil.example"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error_code"], "CSRF_ORIGIN_DENIED")
        self.assertEqual(self.writes, 0)

    def test_allowed_origin_with_cookie_writes(self):
        response = self.client.post(
            "/change",
            json={"enabled": False},
            cookies={"access_token": "session"},
            headers={"Origin": "https://argus.example"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.writes, 1)

    def test_bearer_without_cookie_is_unchanged(self):
        response = self.client.post(
            "/change",
            headers={"Origin": "https://evil.example", "Authorization": "Bearer token"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.writes, 1)

    def test_bearer_does_not_override_cookie_gate(self):
        response = self.client.post(
            "/change",
            cookies={"access_token": "session"},
            headers={"Origin": "https://evil.example", "Authorization": "Bearer token"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.writes, 0)

    def test_missing_origin_with_cookie_is_rejected(self):
        response = self.client.post(
            "/change",
            json={"enabled": False},
            cookies={"access_token": "session"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error_code"], "CSRF_ORIGIN_DENIED")
        self.assertEqual(self.writes, 0)

    def test_api_key_without_cookie_is_unchanged(self):
        response = self.client.post(
            "/change",
            headers={"Origin": "https://evil.example", "X-API-Key": "argus_test_key"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.writes, 1)

    def test_api_key_does_not_override_cookie_gate(self):
        response = self.client.post(
            "/change",
            cookies={"refresh_token": "session"},
            headers={"Origin": "https://evil.example", "X-API-Key": "argus_test_key"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.writes, 0)


if __name__ == "__main__":
    unittest.main()
