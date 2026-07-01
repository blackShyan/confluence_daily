import json
import unittest

from confluence_daily.config import AppConfig
from confluence_daily.confluence_client import ConfluenceClient


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)
        self.content = self.text.encode("utf-8")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self):
        self.auth = None
        self.headers = {}
        self.requests = []
        self.cookies = FakeCookieJar()

    def request(self, method, url, timeout=60, **kwargs):
        self.requests.append(
            {
                "method": method,
                "url": url,
                "timeout": timeout,
                "kwargs": kwargs,
                "headers": dict(self.headers),
                "auth": self.auth,
            }
        )
        if method == "POST":
            return FakeResponse({"id": "999"})
        return FakeResponse(
            {
                "id": "1234567890",
                "title": "parent",
                "body": {"storage": {"value": "<p>x</p>"}},
                "version": {"number": 7},
                "_links": {"base": "https://confluence.example.com", "webui": "/spaces/TEAM/pages/1234567890/x"},
            }
        )


class FakeCookieJar:
    def __init__(self):
        self.cookies = []

    def set(self, name, value, **kwargs):
        self.cookies.append((name, value, kwargs))

    def __iter__(self):
        for name, value, kwargs in self.cookies:
            yield type(
                "Cookie",
                (),
                {
                    "name": name,
                    "value": value,
                    "domain": kwargs.get("domain", ""),
                    "path": kwargs.get("path", "/"),
                },
            )()


class ConfluenceClientTests(unittest.TestCase):
    def test_data_center_can_use_browser_session_cookies(self):
        config = AppConfig(
            base_url="https://confluence.example.com",
            email="user@example.com",
            api_mode="data_center",
            space_key="TEAM",
            parent_page_id="1234567890",
        )
        session = FakeSession()
        cookies = json.dumps(
            [
                {
                    "name": "JSESSIONID",
                    "value": "abc",
                    "domain": "confluence.example.com",
                    "path": "/",
                }
            ]
        )
        client = ConfluenceClient(config, session=session, session_cookies=cookies)

        client.get_page("1234567890")

        request = session.requests[0]
        self.assertEqual(request["url"], "https://confluence.example.com/rest/api/content/1234567890")
        self.assertEqual(session.cookies.cookies[0][0], "JSESSIONID")
        self.assertEqual(session.cookies.cookies[0][1], "abc")
        self.assertNotIn("Authorization", request["headers"])
        self.assertIsNone(request["auth"])

    def test_data_center_create_page_uses_space_key_and_ancestor(self):
        config = AppConfig(
            base_url="https://confluence.example.com",
            email="user@example.com",
            api_mode="data_center",
            space_key="TEAM",
            parent_page_id="1234567890",
        )
        session = FakeSession()
        cookies = json.dumps(
            [
                {
                    "name": "JSESSIONID",
                    "value": "abc",
                    "domain": "confluence.example.com",
                    "path": "/",
                }
            ]
        )
        client = ConfluenceClient(config, session=session, session_cookies=cookies)

        client.create_page("daily", "<p>body</p>")

        request = session.requests[0]
        self.assertEqual(request["method"], "POST")
        self.assertEqual(request["url"], "https://confluence.example.com/rest/api/content")
        self.assertEqual(request["kwargs"]["json"]["space"]["key"], "TEAM")
        self.assertEqual(request["kwargs"]["json"]["ancestors"], [{"id": "1234567890"}])

    def test_data_center_exports_session_cookies_after_request(self):
        config = AppConfig(
            base_url="https://confluence.example.com",
            email="user@example.com",
            api_mode="data_center",
            space_key="TEAM",
            parent_page_id="1234567890",
        )
        session = FakeSession()
        cookies = json.dumps(
            [
                {
                    "name": "JSESSIONID",
                    "value": "abc",
                    "domain": "confluence.example.com",
                    "path": "/",
                }
            ]
        )
        client = ConfluenceClient(config, session=session, session_cookies=cookies)

        exported = json.loads(client.export_session_cookies())

        self.assertEqual(exported[0]["name"], "JSESSIONID")
        self.assertEqual(exported[0]["value"], "abc")
        self.assertEqual(exported[0]["domain"], "confluence.example.com")

    def test_cloud_uses_basic_auth_and_wiki_v2_url(self):
        config = AppConfig(
            base_url="https://example.atlassian.net",
            email="me@example.com",
            api_mode="cloud",
            space_id="123",
            parent_page_id="456",
        )
        session = FakeSession()
        client = ConfluenceClient(config, "secret", session=session)

        client.get_page("789")

        request = session.requests[0]
        self.assertEqual(request["url"], "https://example.atlassian.net/wiki/api/v2/pages/789")
        self.assertEqual(request["auth"], ("me@example.com", "secret"))
        self.assertNotIn("Authorization", request["headers"])


if __name__ == "__main__":
    unittest.main()
