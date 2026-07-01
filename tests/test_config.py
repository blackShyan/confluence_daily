import tempfile
import unittest
from pathlib import Path

from confluence_daily.config import AppConfig, load_config, save_config


class ConfigTests(unittest.TestCase):
    def test_theme_mode_round_trips(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            save_config(AppConfig(theme_mode="dark"), path)

            self.assertEqual(load_config(path).theme_mode, "dark")

    def test_invalid_theme_mode_falls_back_to_light(self):
        self.assertEqual(AppConfig(theme_mode="unknown").effective_theme_mode, "light")

    def test_update_settings_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            save_config(
                AppConfig(
                    update_source_path=r"\\server\share\ConfluenceDailyUploader",
                    check_updates_on_startup=False,
                ),
                path,
            )

            loaded = load_config(path)

            self.assertEqual(loaded.update_source_path, r"\\server\share\ConfluenceDailyUploader")
            self.assertFalse(loaded.check_updates_on_startup)


if __name__ == "__main__":
    unittest.main()
