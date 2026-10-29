from __future__ import annotations

import io
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from unittest.mock import patch

from backend.domain import (
    calculate_plan,
    default_profile,
    process_due_payouts,
    next_payout_date,
    normalize_uganda_phone,
)
from backend.storage import load_workspace, save_workspace, supabase_request


class DomainTests(unittest.TestCase):
    def test_normalize_uganda_phone_accepts_local_and_country_code_forms(self) -> None:
        self.assertEqual(normalize_uganda_phone("0772 123 456"), "+256772123456")
        self.assertEqual(normalize_uganda_phone("+256 772 123 456"), "+256772123456")
        self.assertIsNone(normalize_uganda_phone("0712 123"))

    def test_calculate_plan_uses_daily_and_weekly_costs(self) -> None:
        plan = calculate_plan(10_000, 4, 100, 20, 70, "Monthly")

        self.assertEqual(plan["daily_baseline"], 130)
        self.assertEqual(plan["duration_days"], 28)
        self.assertEqual(plan["payout_amount"], 3_900)
        self.assertEqual(plan["coverage_days"], 10_000 / 130)
        self.assertEqual(plan["required_deposit"], 3_640)

    def test_next_daily_payout_respects_scheduled_time(self) -> None:
        profile = {**default_profile(), "payout_frequency": "Daily"}
        before_payout = datetime(2026, 10, 29, 6, 0, tzinfo=ZoneInfo("Africa/Kampala"))
        after_payout = datetime(2026, 10, 29, 8, 0, tzinfo=ZoneInfo("Africa/Kampala"))

        self.assertEqual(next_payout_date(profile, before_payout).isoformat(), "2026-10-29")
        self.assertEqual(next_payout_date(profile, after_payout).isoformat(), "2026-10-30")

    def test_next_weekly_payout_uses_selected_weekday(self) -> None:
        profile = {
            **default_profile(),
            "payout_frequency": "Weekly",
            "deposit_day": "Wednesday",
        }
        now = datetime(2026, 10, 29, 6, 0, tzinfo=ZoneInfo("Africa/Kampala"))

        self.assertEqual(next_payout_date(profile, now).isoformat(), "2026-11-04")

    def test_next_monthly_payout_rolls_over_to_following_month(self) -> None:
        profile = {
            **default_profile(),
            "payout_frequency": "Monthly",
            "deposit_day_of_month": 1,
        }
        now = datetime(2026, 10, 29, 6, 0, tzinfo=ZoneInfo("Africa/Kampala"))

        self.assertEqual(next_payout_date(profile, now).isoformat(), "2026-11-01")

    def test_due_payout_reduces_balance_and_is_not_recorded_twice(self) -> None:
        profile = {
            **default_profile(),
            "locked": True,
            "vault_balance": 18_000,
            "daily_food": 1_000,
            "payout_frequency": "Weekly",
            "deposit_day": "Wednesday",
            "next_payout_at": "2026-10-28T07:00:00+03:00",
        }
        now = datetime(2026, 10, 29, 8, 0, tzinfo=ZoneInfo("Africa/Kampala"))

        due = process_due_payouts(profile, now)
        replay = process_due_payouts(profile, now)

        self.assertEqual(len(due), 1)
        self.assertEqual(due[0]["amount"], 7_000)
        self.assertEqual(profile["vault_balance"], 11_000)
        self.assertEqual(len(profile["transactions"]), 1)
        self.assertEqual(replay, [])

    def test_due_payout_is_capped_at_remaining_balance(self) -> None:
        profile = {
            **default_profile(),
            "locked": True,
            "vault_balance": 3_000,
            "daily_food": 1_000,
            "payout_frequency": "Weekly",
            "deposit_day": "Wednesday",
            "next_payout_at": "2026-10-28T07:00:00+03:00",
        }
        now = datetime(2026, 10, 29, 8, 0, tzinfo=ZoneInfo("Africa/Kampala"))

        due = process_due_payouts(profile, now)

        self.assertEqual(due[0]["amount"], 3_000)
        self.assertEqual(profile["vault_balance"], 0)
        self.assertIsNone(profile["next_payout_at"])


class StorageTests(unittest.TestCase):
    def test_authenticated_workspaces_round_trip_in_sqlite(self) -> None:
        profile = {"name": "Student", "total_funds": 25_000}
        workflow = {"signup_complete": True}

        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "campusflow.db"
            save_workspace(
                "student-1", profile, workflow, True, "", "", database_path
            )
            loaded_profile, loaded_workflow = load_workspace(
                "student-1", True, "", "", database_path
            )

        self.assertEqual(loaded_profile, profile)
        self.assertEqual(loaded_workflow, workflow)

    def test_demo_workspace_does_not_read_or_write_database(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "campusflow.db"
            profile, workflow = load_workspace(
                "demo-user", False, "", "", database_path
            )
            save_workspace(
                "demo-user", profile, workflow, False, "", "", database_path
            )

            self.assertFalse(database_path.exists())

    def test_supabase_request_uses_bearer_service_key(self) -> None:
        with patch("backend.storage.urlopen", return_value=io.BytesIO(b"[]")) as open_url:
            supabase_request(
                "GET", "https://example.supabase.co", "service-key", "workspaces"
            )

        request = open_url.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer service-key")
        self.assertEqual(request.get_header("Apikey"), "service-key")


if __name__ == "__main__":
    unittest.main()
