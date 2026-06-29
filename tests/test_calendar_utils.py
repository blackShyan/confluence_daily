import unittest
from datetime import date

from confluence_daily.calendar_utils import (
    dates_for_week,
    first_workweek_monday,
    format_date_label,
    month_page_title,
    report_month_for_date,
    row_index_for_date,
    week_number_for_date,
    weeks_in_month,
)


class CalendarUtilsTests(unittest.TestCase):
    def test_july_2026_has_five_workweeks(self):
        self.assertEqual(first_workweek_monday(2026, 7), date(2026, 6, 29))
        self.assertEqual(weeks_in_month(2026, 7), 5)
        self.assertEqual(week_number_for_date(date(2026, 7, 1)), 1)
        self.assertEqual(week_number_for_date(date(2026, 7, 27)), 5)
        self.assertEqual(row_index_for_date(date(2026, 7, 29)), 2)

    def test_month_starting_weekend_skips_empty_workweek(self):
        self.assertEqual(first_workweek_monday(2026, 2), date(2026, 2, 2))
        self.assertEqual(week_number_for_date(date(2026, 2, 2)), 1)

    def test_dates_for_week_masks_days_outside_month(self):
        days = dates_for_week(2026, 7, 1)
        self.assertEqual(days[:2], (None, None))
        self.assertEqual(days[2], date(2026, 7, 1))

    def test_format_date_label(self):
        self.assertEqual(format_date_label(date(2026, 7, 1)), "7/1(\uc218)")

    def test_month_page_title(self):
        self.assertEqual(month_page_title("\uc0ac\uc6a9\uc790", date(2026, 7, 1)), "\uc0ac\uc6a9\uc790_2026\ub144 7\uc6d4")

    def test_report_month_can_follow_workweek_end_month(self):
        self.assertEqual(report_month_for_date(date(2026, 6, 29)), date(2026, 7, 1))
        self.assertEqual(report_month_for_date(date(2026, 6, 30)), date(2026, 7, 1))
        self.assertEqual(report_month_for_date(date(2026, 7, 1)), date(2026, 7, 1))

    def test_report_month_can_follow_selected_date_month(self):
        self.assertEqual(report_month_for_date(date(2026, 6, 29), "date_month"), date(2026, 6, 1))

    def test_weekend_rejected(self):
        with self.assertRaises(ValueError):
            week_number_for_date(date(2026, 7, 4))


if __name__ == "__main__":
    unittest.main()
