import unittest

from confluence_daily.config import AppConfig
from confluence_daily.ui import confluence_site_url


class UiHelperTests(unittest.TestCase):
    def test_data_center_site_url_prefers_parent_page(self):
        config = AppConfig(
            base_url="https://confluence.example.com/",
            api_mode="data_center",
            parent_page_id="1234567890",
        )

        self.assertEqual(
            confluence_site_url(config),
            "https://confluence.example.com/pages/viewpage.action?pageId=1234567890",
        )

    def test_site_url_falls_back_to_base_url(self):
        config = AppConfig(base_url="https://confluence.example.com/")

        self.assertEqual(confluence_site_url(config), "https://confluence.example.com")

    def test_cloud_site_url_uses_wiki_page_path(self):
        config = AppConfig(
            base_url="https://example.atlassian.net",
            api_mode="cloud",
            parent_page_id="456",
        )

        self.assertEqual(confluence_site_url(config), "https://example.atlassian.net/wiki/pages/456")

    def test_cloud_site_url_does_not_duplicate_wiki_prefix(self):
        config = AppConfig(
            base_url="https://example.atlassian.net/wiki/",
            api_mode="cloud",
            parent_page_id="456",
        )

        self.assertEqual(confluence_site_url(config), "https://example.atlassian.net/wiki/pages/456")


if __name__ == "__main__":
    unittest.main()
