import itertools
import unittest
from unittest import mock

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import config
from service import auth

KEY = "9f81ba760235e4cd7b60a19dca57e8234802bf6159ce743a182b9fdce03657a4"
OTHER_KEY = "5" + KEY[1:]


class ServiceAuthTest(unittest.TestCase):
    def setUp(self) -> None:
        app = FastAPI()
        app.add_middleware(auth.ServiceAuthMiddleware)
        self.work = mock.Mock()

        @app.api_route("/protected", methods=["GET", "POST", "OPTIONS"])
        def protected(request: Request):
            self.work()
            return {"authenticated": request.state.service_authenticated}

        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.logs = self.enterContext(mock.patch.object(auth.logger, "warning"))

    def test_complete_configuration_and_header_matrix(self) -> None:
        headers = (None, KEY, OTHER_KEY, "", "bad", [KEY, KEY])
        for env, flag, key, header in itertools.product(
                ("production", "development", "unknown", "Development", ""),
                ("0", "1", "true", ""), (KEY, None, "", "placeholder", "0" * 64), headers):
            with self.subTest(env=env, flag=flag, key_kind=key is None,
                              header_kind=type(header).__name__):
                supplied = ([] if header is None else
                            [("X-NexMate-Key", h) for h in header] if isinstance(header, list)
                            else [("X-NexMate-Key", header)])
                allowed = (key == KEY and header == KEY) or (
                    env == "development" and flag == "1"
                    and key in (KEY, None) and header is None)
                self.work.reset_mock()
                with mock.patch.multiple(config, NEXMATE_ENV=env,
                                         NEXMATE_DEV_UNAUTHENTICATED=flag,
                                         NEXMATE_SERVICE_KEY=key):
                    response = self.client.get("/protected", headers=supplied)
                self.assertEqual(response.status_code == 200, allowed)
                self.assertEqual(self.work.call_count, int(allowed))
                if allowed:
                    self.assertEqual(response.json()["authenticated"], header == KEY)
                self.assertNotIn(KEY, response.text)
                self.assertNotIn(OTHER_KEY, response.text)
        self.assertNotIn(KEY, str(self.logs.call_args_list))
        self.assertNotIn("X-NexMate-Key", str(self.logs.call_args_list))

    def test_health_is_fixed_before_every_auth_check(self) -> None:
        for key, env, method in itertools.product(
                (KEY, None, "", "broken"), ("production", "development", "bad"),
                ("GET", "POST", "OPTIONS")):
            with mock.patch.multiple(config, NEXMATE_SERVICE_KEY=key, NEXMATE_ENV=env):
                response = self.client.request(method, "/health", headers=[
                    ("X-NexMate-Key", ""), ("X-NexMate-Key", "bad")])
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {"status": "ok"})
        self.logs.assert_not_called()
        self.work.assert_not_called()

    def test_paths_methods_and_request_heuristics_do_not_bypass(self) -> None:
        with mock.patch.multiple(config, NEXMATE_SERVICE_KEY=KEY,
                                 NEXMATE_ENV="production", NEXMATE_DEV_UNAUTHENTICATED="1"):
            for path, method in itertools.product(
                    ("/health/", "/health-extra", "/unknown", "/docs", "/redoc",
                     "/openapi.json", "/ui/preview.html", "/protected"),
                    ("GET", "POST", "OPTIONS")):
                response = self.client.request(method, path + "?NEXMATE_ENV=development",
                    headers={"Origin": "http://localhost", "Host": "localhost",
                             "X-Forwarded-For": "127.0.0.1", "X-NexMate-Env": "development",
                             "X-NexMate-Dev-Unauthenticated": "1",
                             "Access-Control-Request-Method": "POST"})
                self.assertEqual(response.status_code, 401)
        self.work.assert_not_called()

    def test_constant_time_byte_comparison(self) -> None:
        with mock.patch.multiple(config, NEXMATE_SERVICE_KEY=KEY, NEXMATE_ENV="production"), \
                mock.patch.object(auth.hmac, "compare_digest", wraps=auth.hmac.compare_digest) as compare:
            for candidate in (KEY, OTHER_KEY):
                self.client.get("/protected", headers={"X-NexMate-Key": candidate})
                compare.assert_called_with(candidate.encode("ascii"), KEY.encode("ascii"))

    def test_configured_key_validation(self) -> None:
        for key in (None, "", " ", "changeme", "a" * 64, "abcd" * 16,
                    "g" * 64, KEY + "\n", KEY[:-1], 123):
            self.assertFalse(auth.valid_service_key(key))
        self.assertTrue(auth.valid_service_key(KEY))
        self.assertTrue(auth.valid_service_key(KEY.upper()))


if __name__ == "__main__":
    unittest.main()
