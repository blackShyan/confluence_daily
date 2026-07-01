import json
import tempfile
import unittest
from pathlib import Path

from confluence_daily.updater import (
    APP_EXE_NAME,
    UpdateError,
    UpdateInfo,
    compare_versions,
    find_update,
    load_update_info,
    stage_update,
)


class UpdaterTests(unittest.TestCase):
    def test_compare_versions_uses_numeric_parts(self):
        self.assertGreater(compare_versions("0.1.10", "0.1.2"), 0)
        self.assertEqual(compare_versions("v1.2.0", "1.2"), 0)
        self.assertLess(compare_versions("1.0.0", "1.0.1"), 0)

    def test_load_update_info_uses_relative_distribution_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dist = root / "DailyBuild"
            dist.mkdir()
            (dist / APP_EXE_NAME).write_text("exe", encoding="utf-8")
            (root / "latest.json").write_text(
                json.dumps({"version": "0.2.0", "folder": "DailyBuild", "notes": "changed"}),
                encoding="utf-8",
            )

            info = load_update_info(str(root))

            self.assertEqual(info.version, "0.2.0")
            self.assertEqual(info.source_dir, dist.resolve())
            self.assertEqual(info.notes, "changed")

    def test_load_update_info_rejects_empty_source_path(self):
        with self.assertRaisesRegex(UpdateError, "업데이트 경로"):
            load_update_info("")

    def test_load_update_info_accepts_utf8_bom_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dist = root / "ConfluenceDailyUploader"
            dist.mkdir()
            (dist / APP_EXE_NAME).write_text("exe", encoding="utf-8")
            payload = json.dumps({"version": "0.2.0"}).encode("utf-8")
            (root / "latest.json").write_bytes(b"\xef\xbb\xbf" + payload)

            info = load_update_info(str(root))

            self.assertEqual(info.version, "0.2.0")

    def test_find_update_returns_none_for_same_or_older_version(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dist = root / "ConfluenceDailyUploader"
            dist.mkdir()
            (dist / APP_EXE_NAME).write_text("exe", encoding="utf-8")
            (root / "latest.json").write_text(json.dumps({"version": "0.1.0"}), encoding="utf-8")

            self.assertIsNone(find_update(str(root), "0.1.0"))
            self.assertIsNone(find_update(str(root), "0.2.0"))

    def test_stage_update_copies_distribution_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            source.mkdir()
            (source / APP_EXE_NAME).write_text("exe", encoding="utf-8")
            (source / "_internal").mkdir()
            (source / "_internal" / "lib.dll").write_text("dll", encoding="utf-8")
            manifest = root / "latest.json"
            manifest.write_text("{}", encoding="utf-8")
            info = UpdateInfo(version="0.2.0", source_dir=source, manifest_path=manifest)

            staged = stage_update(info, root / "staged")

            self.assertTrue((staged / APP_EXE_NAME).exists())
            self.assertTrue((staged / "_internal" / "lib.dll").exists())

    def test_load_update_info_requires_exe(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "ConfluenceDailyUploader").mkdir()
            (root / "latest.json").write_text(json.dumps({"version": "0.2.0"}), encoding="utf-8")

            with self.assertRaises(UpdateError):
                load_update_info(str(root))

if __name__ == "__main__":
    unittest.main()
