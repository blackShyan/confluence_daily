import unittest
from datetime import date
from pathlib import Path

from confluence_daily.config import AppConfig
from confluence_daily.models import DailyInput, PagePayload
from confluence_daily.uploader import DailyUploader


class FakeClient:
    def __init__(self):
        self.find_titles = []
        self.created_pages = []
        self.uploads = []
        self.updated_pages = []

    def find_page_by_title(self, title):
        self.find_titles.append(title)
        return None

    def create_page(self, title, storage):
        self.created_pages.append((title, storage))
        return PagePayload("page-1", title, 1, storage, "https://example.test/page-1")

    def get_page(self, page_id):
        raise AssertionError("get_page should not be called when create_page returns the page.")

    def upload_attachment(self, page_id, source_path, attachment_name):
        self.uploads.append((page_id, source_path, attachment_name))

    def update_page(self, page, storage, message=""):
        self.updated_pages.append((page.title, storage, message))
        return PagePayload(page.page_id, page.title, page.version + 1, storage, page.web_url)


class FakeState:
    def __init__(self):
        self.uploaded = []

    def mark_uploaded(self, work_date, page_id, page_url):
        self.uploaded.append((work_date, page_id, page_url))


class UploaderTests(unittest.TestCase):
    def test_workweek_end_month_policy_uses_next_month_page(self):
        config = AppConfig(
            base_url="https://confluence.example.com",
            email="user@example.com",
            api_mode="data_center",
            space_key="TEAM",
            parent_page_id="1234567890",
            user_name="\uc0ac\uc6a9\uc790",
            month_page_policy="workweek_end_month",
        )
        client = FakeClient()
        state = FakeState()
        uploader = DailyUploader(config, client=client, state=state)

        uploader.upload(DailyInput(date(2026, 6, 29), tuple(), "comment"), "overwrite")

        self.assertEqual(client.find_titles[0], "\uc0ac\uc6a9\uc790_2026\ub144 7\uc6d4")
        self.assertIn('datetime="2026-06-29"', client.updated_pages[0][1])

    def test_text_mode_upload_skips_attachments_and_writes_work_body(self):
        config = AppConfig(
            base_url="https://confluence.example.com",
            email="user@example.com",
            api_mode="data_center",
            space_key="TEAM",
            parent_page_id="1234567890",
            user_name="\uc0ac\uc6a9\uc790",
            month_page_policy="date_month",
        )
        client = FakeClient()
        state = FakeState()
        uploader = DailyUploader(config, client=client, state=state)

        uploader.upload(
            DailyInput(
                date(2026, 7, 1),
                (Path("shot.png"),),
                "",
                content_mode="text",
                text_body="회의 정리\n문서 업데이트",
            ),
            "overwrite",
        )

        self.assertEqual(client.uploads, [])
        self.assertIn("회의 정리", client.updated_pages[0][1])
        self.assertIn("문서 업데이트", client.updated_pages[0][1])
        self.assertNotIn("shot.png", client.updated_pages[0][1])


if __name__ == "__main__":
    unittest.main()
