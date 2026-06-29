import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from confluence_daily.state import DailyState


class DailyStateTests(unittest.TestCase):
    def test_mark_notified_clears_elapsed_snooze(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state = DailyState(Path(temp_dir) / "state.sqlite3")
            work_date = date(2026, 7, 1)
            state.set_snooze_until(work_date, datetime.now() + timedelta(minutes=10))

            self.assertIsNotNone(state.snooze_until(work_date))
            state.mark_notified(work_date)
            self.assertIsNone(state.snooze_until(work_date))
            self.assertIsNotNone(state.last_notified_at(work_date))

    def test_uploaded_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state = DailyState(Path(temp_dir) / "state.sqlite3")
            work_date = date(2026, 7, 1)

            self.assertFalse(state.is_uploaded(work_date))
            state.mark_uploaded(work_date, "123", "https://example.test/page")
            self.assertTrue(state.is_uploaded(work_date))


if __name__ == "__main__":
    unittest.main()

