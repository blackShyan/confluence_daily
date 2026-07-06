import unittest
from datetime import date
from pathlib import Path

from confluence_daily.models import DailyEntryConflict, UploadedAttachment
from confluence_daily.page_builder import (
    build_month_storage,
    has_daily_conflict,
    update_storage_for_entry,
    update_storage_for_entry_for_month,
)


class PageBuilderTests(unittest.TestCase):
    def test_build_month_storage_creates_five_weeks_for_july_2026(self):
        storage = build_month_storage(2026, 7)
        self.assertIn("1\uc8fc\ucc28", storage)
        self.assertIn("5\uc8fc\ucc28", storage)
        self.assertEqual(storage.count("\uc5c5\ubb34 \ub0b4\uc6a9"), 5)
        self.assertIn('<table class="wrapped">', storage)
        self.assertIn("<tbody>", storage)

    def test_update_row_adds_time_macro_image_and_comment(self):
        storage = build_month_storage(2026, 7)
        attachment = UploadedAttachment(Path("shot.png"), "20260701_abcd_shot.png", "image")

        updated = update_storage_for_entry(
            storage,
            date(2026, 7, 1),
            (attachment,),
            "rig check\nsequence check",
        )

        self.assertIn('datetime="2026-07-01"', updated)
        self.assertIn('ac:height="250"', updated)
        self.assertIn('ac:thumbnail="true"', updated)
        self.assertIn("20260701_abcd_shot.png", updated)
        self.assertIn("rig check", updated)
        self.assertIn("sequence check", updated)
        self.assertTrue(has_daily_conflict(updated, date(2026, 7, 1)))

    def test_video_uses_confluence_view_file_macro(self):
        storage = build_month_storage(2026, 7)
        attachment = UploadedAttachment(Path("clip.mp4"), "clip.mp4", "video")

        updated = update_storage_for_entry(storage, date(2026, 7, 1), (attachment,), "video work")

        self.assertIn('ac:name="view-file"', updated)
        self.assertIn("clip.mp4", updated)
        self.assertIn("<ac:parameter ac:name=\"height\">250</ac:parameter>", updated)

    def test_text_only_work_body_goes_to_work_cell_without_attachment(self):
        storage = build_month_storage(2026, 7)

        updated = update_storage_for_entry(
            storage,
            date(2026, 7, 1),
            tuple(),
            "",
            work_text="rig check\nsequence check",
        )

        self.assertIn('datetime="2026-07-01"', updated)
        self.assertIn("rig check", updated)
        self.assertIn("sequence check", updated)
        self.assertNotIn("ac:attachment", updated)
        self.assertTrue(has_daily_conflict(updated, date(2026, 7, 1)))

    def test_existing_tbody_table_is_updated_in_place(self):
        storage = """
<ac:structured-macro ac:name="expand" ac:schema-version="1">
  <ac:parameter ac:name="title">1\uc8fc\ucc28</ac:parameter>
  <ac:rich-text-body>
    <table class="wrapped"><colgroup><col /><col /><col /></colgroup><tbody>
      <tr><th>\ub0a0\uc9dc</th><th>\uc5c5\ubb34 \ub0b4\uc6a9</th><th>\ucc38\uace0</th></tr>
      <tr><td><div class="content-wrapper"><p><time datetime="2026-06-29" />&#160;</p></div></td><td><br /></td><td><br /></td></tr>
      <tr><td><div class="content-wrapper"><p><time datetime="2026-06-30" />&#160;</p></div></td><td><br /></td><td><br /></td></tr>
      <tr><td><br /></td><td><br /></td><td><br /></td></tr>
      <tr><td><br /></td><td><br /></td><td><br /></td></tr>
      <tr><td><br /></td><td><br /></td><td><br /></td></tr>
    </tbody></table>
  </ac:rich-text-body>
</ac:structured-macro>
"""
        attachment = UploadedAttachment(Path("shot.png"), "shot.png", "image")

        updated = update_storage_for_entry(storage, date(2026, 7, 1), (attachment,), "filled")

        self.assertEqual(updated.count("<tbody>"), 5)
        self.assertEqual(updated.count("<tr>"), 30)
        self.assertEqual(updated.count('datetime="2026-07-01"'), 1)
        self.assertIn('datetime="2026-07-01"', updated)
        self.assertIn("shot.png", updated)
        self.assertIn("filled", updated)

    def test_previous_month_date_can_fill_next_month_first_week(self):
        storage = build_month_storage(2026, 7)
        attachment = UploadedAttachment(Path("shot.png"), "shot.png", "image")

        updated = update_storage_for_entry_for_month(
            storage,
            date(2026, 6, 29),
            (attachment,),
            "july week one",
            2026,
            7,
        )

        self.assertIn('datetime="2026-06-29"', updated)
        self.assertIn("shot.png", updated)
        self.assertIn("july week one", updated)

    def test_conflict_cancel_raises(self):
        storage = build_month_storage(2026, 7)
        attachment = UploadedAttachment(Path("shot.png"), "shot.png", "image")
        updated = update_storage_for_entry(storage, date(2026, 7, 1), (attachment,), "done")

        with self.assertRaises(DailyEntryConflict):
            update_storage_for_entry(updated, date(2026, 7, 1), (attachment,), "again", "cancel")

    def test_conflict_append_preserves_existing_content(self):
        storage = build_month_storage(2026, 7)
        first = UploadedAttachment(Path("first.mp4"), "first.mp4", "video")
        second = UploadedAttachment(Path("second.mp4"), "second.mp4", "video")

        updated = update_storage_for_entry(storage, date(2026, 7, 1), (first,), "first")
        appended = update_storage_for_entry(updated, date(2026, 7, 1), (second,), "second", "append")

        self.assertIn("first.mp4", appended)
        self.assertIn("second.mp4", appended)
        self.assertIn("first", appended)
        self.assertIn("second", appended)


if __name__ == "__main__":
    unittest.main()
