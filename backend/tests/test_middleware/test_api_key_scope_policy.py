"""Regression tests for the API-key route allowlist."""

import unittest

from app.core.api_key_scopes import api_key_allows, required_api_key_scope


class TestAPIKeyScopePolicy(unittest.TestCase):
    def test_read_event_routes(self):
        for path in (
            "/api/v1/events",
            "/api/v1/events/",
            "/api/v1/events/export",
            "/api/v1/events/id-123/frames/1",
            "/api/v1/events/id-123/video",
            "/api/v1/thumbnails/2026-09-23/event.jpg",
        ):
            with self.subTest(path=path):
                self.assertEqual(required_api_key_scope("GET", path), "read:events")
                self.assertEqual(required_api_key_scope("HEAD", path), "read:events")

    def test_event_mutations_require_admin(self):
        for method, path in (
            ("POST", "/api/v1/events"),
            ("DELETE", "/api/v1/events/bulk"),
            ("DELETE", "/api/v1/events/id-123"),
            ("POST", "/api/v1/events/id-123/reanalyze"),
        ):
            with self.subTest(method=method, path=path):
                self.assertEqual(required_api_key_scope(method, path), "admin")

    def test_camera_reads_and_management(self):
        self.assertEqual(required_api_key_scope("GET", "/api/v1/cameras"), "read:cameras")
        self.assertEqual(required_api_key_scope("GET", "/api/v1/cameras/id-123/preview"), "read:cameras")
        for method, path in (
            ("POST", "/api/v1/cameras"),
            ("PUT", "/api/v1/cameras/id-123"),
            ("DELETE", "/api/v1/cameras/id-123"),
            ("POST", "/api/v1/cameras/id-123/reconnect"),
            ("PUT", "/api/v1/cameras/id-123/motion/config"),
            ("PATCH", "/api/v1/cameras/id-123/audio"),
        ):
            with self.subTest(method=method, path=path):
                self.assertEqual(required_api_key_scope(method, path), "write:cameras")

    def test_static_routes_do_not_inherit_parameter_scopes(self):
        self.assertEqual(required_api_key_scope("GET", "/api/v1/events/export"), "read:events")
        self.assertEqual(required_api_key_scope("DELETE", "/api/v1/events/bulk"), "admin")
        self.assertIsNone(required_api_key_scope("POST", "/api/v1/cameras/id-123/analyze"))
        self.assertIsNone(required_api_key_scope("POST", "/api/v1/cameras/id-123/test"))
        self.assertIsNone(required_api_key_scope("OPTIONS", "/api/v1/events"))
        self.assertIsNone(required_api_key_scope("GET", "/api/v1/events/../system/data"))

    def test_batch_and_export_routes_outside_the_allowlist_are_denied(self):
        for method, path in (
            ("GET", "/api/v1/motion-events/export"),
            ("GET", "/api/v1/webhooks/logs/export"),
            ("GET", "/api/v1/context/adjustments/export"),
            ("POST", "/api/v1/context/embeddings/batch"),
            ("POST", "/api/v1/context/patterns/batch"),
            ("DELETE", "/api/v1/motion-events/id-123"),
        ):
            with self.subTest(method=method, path=path):
                self.assertIsNone(required_api_key_scope(method, path))
                self.assertFalse(api_key_allows(["admin"], required_api_key_scope(method, path)))

    def test_unlisted_routes_are_denied_even_with_admin_scope(self):
        for method, path in (
            ("DELETE", "/api/v1/system/data"),
            ("POST", "/api/v1/system/restore"),
            ("GET", "/api/v1/system/backup/list"),
            ("GET", "/api/v1/users"),
            ("POST", "/api/v1/api-keys"),
            ("POST", "/api/v1/cameras/discover"),
            ("POST", "/api/v1/cameras/id-123/analyze"),
            ("GET", "/api/v1/events-extra"),
            ("GET", "/api/v1/cameras-extra"),
        ):
            with self.subTest(method=method, path=path):
                self.assertIsNone(required_api_key_scope(method, path))

    def test_custom_prefix(self):
        self.assertEqual(
            required_api_key_scope("GET", "/custom/events", "/custom"),
            "read:events",
        )

    def test_scope_enforcement(self):
        self.assertTrue(api_key_allows(["read:events"], "read:events"))
        self.assertFalse(api_key_allows(["read:events"], "admin"))
        self.assertFalse(api_key_allows(["read:events"], "read:cameras"))
        self.assertTrue(api_key_allows(["admin"], "write:cameras"))
        self.assertFalse(api_key_allows(["admin"], None))
        self.assertFalse(api_key_allows([], "read:events"))


if __name__ == "__main__":
    unittest.main()
