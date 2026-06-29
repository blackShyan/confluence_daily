from __future__ import annotations

import mimetypes
import json
from pathlib import Path
from typing import Any

from .config import AppConfig
from .models import ConfluenceApiError, PagePayload


class ConfluenceClient:
    def __init__(
        self,
        config: AppConfig,
        api_token: str | None = None,
        session: Any | None = None,
        session_cookies: str | None = None,
    ) -> None:
        if session is None:
            try:
                import requests
            except ImportError as exc:
                raise ConfluenceApiError("Install requests to use the Confluence API.") from exc
            session = requests.Session()

        self.config = config
        self.session = session
        if config.is_data_center:
            if session_cookies:
                self._apply_session_cookies(session_cookies)
            else:
                raise ConfluenceApiError("Missing Confluence browser session cookies.")
        else:
            if not api_token:
                raise ConfluenceApiError("Missing Confluence API token.")
            self.session.auth = (config.email, api_token)
        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "ConfluenceDailyUploader/0.1",
            }
        )

    def _apply_session_cookies(self, cookies_json: str) -> None:
        try:
            cookies = json.loads(cookies_json)
        except json.JSONDecodeError as exc:
            raise ConfluenceApiError("Stored browser session cookies are invalid.") from exc

        if not isinstance(cookies, list):
            raise ConfluenceApiError("Stored browser session cookies are invalid.")

        jar = getattr(self.session, "cookies", None)
        if jar is None or not hasattr(jar, "set"):
            raise ConfluenceApiError("HTTP session does not support cookie authentication.")

        for cookie in cookies:
            if not isinstance(cookie, dict):
                continue
            name = str(cookie.get("name") or "")
            value = str(cookie.get("value") or "")
            if not name:
                continue
            domain = str(cookie.get("domain") or "")
            path = str(cookie.get("path") or "/")
            if domain:
                jar.set(name, value, domain=domain, path=path)
            else:
                jar.set(name, value, path=path)

    def find_page_by_title(self, title: str) -> PagePayload | None:
        if self.config.is_data_center:
            return self._dc_find_page_by_title(title)
        return self._cloud_find_page_by_title(title)

    def get_page(self, page_id: str) -> PagePayload:
        if self.config.is_data_center:
            payload = self._request(
                "GET",
                f"/rest/api/content/{page_id}",
                params={"expand": "space,ancestors,body.storage,version"},
            )
            return self._page_from_json(payload)

        payload = self._request(
            "GET",
            f"/api/v2/pages/{page_id}",
            params={"body-format": "storage"},
        )
        return self._page_from_json(payload)

    def create_page(self, title: str, storage: str) -> PagePayload:
        if self.config.is_data_center:
            body: dict[str, Any] = {
                "type": "page",
                "title": title,
                "space": {"key": self.config.effective_space_key},
                "body": {
                    "storage": {
                        "value": storage,
                        "representation": "storage",
                    }
                },
            }
            if self.config.parent_page_id:
                body["ancestors"] = [{"id": self.config.parent_page_id}]
            payload = self._request("POST", "/rest/api/content", json=body)
            return self.get_page(str(payload["id"]))

        body = {
            "spaceId": self.config.space_id,
            "status": "current",
            "title": title,
            "body": {
                "representation": "storage",
                "value": storage,
            },
        }
        if self.config.parent_page_id:
            body["parentId"] = self.config.parent_page_id

        payload = self._request("POST", "/api/v2/pages", json=body)
        return self.get_page(str(payload["id"]))

    def update_page(self, page: PagePayload, storage: str, message: str = "Update daily report") -> PagePayload:
        if self.config.is_data_center:
            payload = {
                "id": page.page_id,
                "type": "page",
                "title": page.title,
                "body": {
                    "storage": {
                        "value": storage,
                        "representation": "storage",
                    }
                },
                "version": {
                    "number": page.version + 1,
                    "message": message,
                },
            }
            self._request("PUT", f"/rest/api/content/{page.page_id}", json=payload)
            return self.get_page(page.page_id)

        payload = {
            "id": page.page_id,
            "status": "current",
            "title": page.title,
            "body": {
                "representation": "storage",
                "value": storage,
            },
            "version": {
                "number": page.version + 1,
                "message": message,
            },
        }
        self._request("PUT", f"/api/v2/pages/{page.page_id}", json=payload)
        return self.get_page(page.page_id)

    def upload_attachment(self, page_id: str, source_path: Path, attachment_name: str) -> None:
        mime_type = mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
        with source_path.open("rb") as handle:
            files = {"file": (attachment_name, handle, mime_type)}
            self._request(
                "POST",
                f"/rest/api/content/{page_id}/child/attachment",
                headers={"X-Atlassian-Token": "no-check"},
                files=files,
            )

    def _cloud_find_page_by_title(self, title: str) -> PagePayload | None:
        payload = self._request(
            "GET",
            "/api/v2/pages",
            params={
                "space-id": self.config.space_id,
                "title": title,
                "body-format": "storage",
                "limit": 25,
            },
        )

        for item in payload.get("results", []):
            if item.get("title") != title:
                continue
            if self.config.parent_page_id and item.get("parentId") not in {self.config.parent_page_id, None}:
                continue
            return self._page_from_json(item)
        return None

    def _dc_find_page_by_title(self, title: str) -> PagePayload | None:
        payload = self._request(
            "GET",
            "/rest/api/content",
            params={
                "spaceKey": self.config.effective_space_key,
                "title": title,
                "type": "page",
                "expand": "space,ancestors,body.storage,version",
                "limit": 25,
            },
        )
        for item in payload.get("results", []):
            if item.get("title") != title:
                continue
            if not self.config.parent_page_id:
                return self._page_from_json(item)
            ancestors = item.get("ancestors") or []
            if any(str(ancestor.get("id")) == self.config.parent_page_id for ancestor in ancestors):
                return self._page_from_json(item)
        return None

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        url = self._url(path)
        response = self.session.request(method, url, timeout=60, **kwargs)
        if response.status_code >= 400:
            body = response.text[:1000] if getattr(response, "text", None) else ""
            raise ConfluenceApiError(f"Confluence API {method} {url} failed: {response.status_code} {body}")

        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    def _url(self, path: str) -> str:
        if self.config.is_data_center:
            return f"{self._base()}{path}"
        return f"{self._wiki_base()}{path}"

    def _base(self) -> str:
        return self.config.base_url.rstrip("/")

    def _wiki_base(self) -> str:
        base = self._base()
        return base if base.endswith("/wiki") else f"{base}/wiki"

    def _page_from_json(self, data: dict[str, Any]) -> PagePayload:
        body = data.get("body", {})
        storage = ""
        if isinstance(body, dict):
            storage_payload = body.get("storage")
            if isinstance(storage_payload, dict):
                storage = storage_payload.get("value") or ""
            else:
                storage = body.get("value") or ""

        version_payload = data.get("version") or {}
        version = int(version_payload.get("number", 1))
        web_url = None
        links = data.get("_links") or {}
        if links.get("webui"):
            base = (links.get("base") or (self._base() if self.config.is_data_center else self._wiki_base())).rstrip("/")
            web_url = base + links["webui"]

        return PagePayload(
            page_id=str(data["id"]),
            title=data.get("title", ""),
            version=version,
            storage=storage,
            web_url=web_url,
        )
