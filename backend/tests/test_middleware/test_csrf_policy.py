"""Focused tests for cookie-authenticated write origin validation."""

import unittest

from app.core.csrf import cookie_write_origin_allowed


ALLOWED = ["https://argus.example", "http://localhost:3000"]


class TestCookieWriteOriginPolicy(unittest.TestCase):
    def check(self, method="POST", cookies=None, headers=None, allowed=None):
        return cookie_write_origin_allowed(
            method,
            set(cookies or []),
            headers or {},
            allowed if allowed is not None else ALLOWED,
        )

    def test_cookie_write_from_trusted_origin_succeeds(self):
        self.assertTrue(self.check(cookies=["access_token"], headers={"origin": ALLOWED[0]}))
        self.assertTrue(self.check(method="DELETE", cookies=["refresh_token"], headers={"origin": ALLOWED[1]}))

    def test_hostile_and_null_origins_fail(self):
        for origin in ("https://evil.example", "null", "https://argus.example.evil.test", "*"):
            with self.subTest(origin=origin):
                self.assertFalse(self.check(cookies=["access_token"], headers={"origin": origin}))

    def test_origin_does_not_fall_back_to_trusted_referer(self):
        self.assertFalse(self.check(
            cookies=["access_token"],
            headers={"origin": "https://evil.example", "referer": "https://argus.example/settings"},
        ))

    def test_missing_origin_requires_valid_referer(self):
        self.assertFalse(self.check(cookies=["access_token"]))
        self.assertTrue(self.check(
            cookies=["access_token"], headers={"referer": "https://argus.example/settings"},
        ))
        for referer in ("https://argus.example.evil.test/", "https://argus.example@evil.test/", "bad"):
            with self.subTest(referer=referer):
                self.assertFalse(self.check(cookies=["access_token"], headers={"referer": referer}))

    def test_safe_or_cookie_free_requests_are_unaffected(self):
        self.assertTrue(self.check(method="GET", cookies=["access_token"], headers={"origin": "https://evil.example"}))
        self.assertTrue(self.check(method="OPTIONS", cookies=["access_token"]))
        self.assertTrue(self.check(method="DELETE", headers={"origin": "https://evil.example"}))

    def test_wildcard_is_not_trusted_for_credentials(self):
        self.assertFalse(self.check(cookies=["access_token"], headers={"origin": "https://evil.example"}, allowed=["*"]))


if __name__ == "__main__":
    unittest.main()
