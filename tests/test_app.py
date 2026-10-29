from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from streamlit.testing.v1 import AppTest

from backend.domain import WORKFLOW_STATE_KEYS, default_profile, next_payout_date

APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")


class AppTests(unittest.TestCase):
    def test_expense_form_rejects_an_all_zero_baseline(self) -> None:
        app = AppTest.from_file(APP_PATH).run()
        app.button[0].click().run()
        app.text_input[0].set_value("Test Student")
        app.text_input[1].set_value("0772 123 456")
        app.button[0].click().run()

        app.button[0].click().run()

        self.assertEqual(
            [element.value for element in app.error],
            ["Enter at least one expense greater than zero before continuing."],
        )
        self.assertEqual([element.value for element in app.title], ["Your everyday expenses"])
        self.assertFalse(app.exception)

    def test_plan_screen_blocks_a_missing_expense_baseline(self) -> None:
        app = AppTest.from_file(APP_PATH, default_timeout=10)
        app.session_state["profile"] = default_profile("Test Student")
        app.session_state["workspace_page"] = "3. Calculate plan"
        app.session_state["signup_complete"] = True
        app.session_state["expenses_complete"] = True

        app.run()

        self.assertEqual([element.value for element in app.title], ["Calculate your allowance plan"])
        self.assertTrue(
            any(
                "Add at least one expense greater than zero" in element.value
                for element in app.warning
            )
        )
        self.assertFalse(any(element.label == "Save this plan" for element in app.button))
        self.assertFalse(app.exception)

    def test_duration_calculator_compares_target_with_actual_available_funds(self) -> None:
        profile = {**default_profile("Test Student"), "daily_food": 10_000}
        app = AppTest.from_file(APP_PATH, default_timeout=10)
        app.session_state["profile"] = profile
        app.session_state["workspace_page"] = "3. Calculate plan"
        app.session_state["signup_complete"] = True
        app.session_state["expenses_complete"] = True

        app.run()
        app.segmented_control[0].set_value("How long I need it to last").run()
        app.number_input[0].set_value(50_000).run()

        metrics = {metric.label: metric.value for metric in app.metric}
        self.assertEqual(metrics["Additional amount needed"], "UGX 230,000")

        save_button = next(button for button in app.button if button.label == "Save this plan")
        save_button.click().run()

        self.assertEqual(app.session_state["profile"]["total_funds"], 50_000)
        self.assertFalse(app.exception)

    def test_overview_shows_next_selected_payout_and_prototype_disclaimer(self) -> None:
        profile = {
            **default_profile("Test Student"),
            "daily_food": 10_000,
            "total_funds": 50_000,
            "payout_frequency": "Weekly",
            "deposit_day": "Wednesday",
        }
        app = AppTest.from_file(APP_PATH, default_timeout=10)
        app.session_state["profile"] = profile
        app.session_state["workspace_page"] = "Overview"
        for step in WORKFLOW_STATE_KEYS:
            app.session_state[step] = True

        app.run()

        expected_date = next_payout_date(profile).strftime("%A, %d %B")
        markdown_values = [element.value for element in app.markdown]
        caption_values = [element.value for element in app.caption]
        self.assertIn(f"### {expected_date}", markdown_values)
        self.assertTrue(any("payouts and SMS are not sent" in value for value in caption_values))
        self.assertTrue(any("No money is moved" in value for value in caption_values))
        self.assertFalse(any("Processed 2 days ago" in value for value in caption_values))
        self.assertFalse(app.exception)

    def test_emergency_withdrawal_updates_balance_and_transaction_history(self) -> None:
        profile = {
            **default_profile("Test Student"),
            "locked": True,
            "vault_balance": 5_000,
        }
        app = AppTest.from_file(APP_PATH, default_timeout=10)
        app.session_state["profile"] = profile
        app.session_state["workspace_page"] = "Emergency withdrawal"
        app.session_state["signup_complete"] = True

        app.run()
        app.number_input[0].set_value(2_000)
        submit_button = next(
            button
            for button in app.button
            if button.label == "Record simulated withdrawal"
        )
        submit_button.click().run()

        saved_profile = app.session_state["profile"]
        self.assertEqual(saved_profile["vault_balance"], 3_000)
        self.assertEqual(len(saved_profile["transactions"]), 1)
        self.assertEqual(saved_profile["transactions"][0]["type"], "Emergency withdrawal")
        self.assertFalse(app.exception)

    def test_due_payout_is_recorded_when_workspace_is_opened(self) -> None:
        now = datetime.now(ZoneInfo("Africa/Kampala"))
        profile = {
            **default_profile("Test Student"),
            "locked": True,
            "vault_balance": 18_000,
            "daily_food": 1_000,
            "payout_frequency": "Daily",
            "next_payout_at": (now - timedelta(minutes=1)).isoformat(),
        }
        app = AppTest.from_file(APP_PATH, default_timeout=10)
        app.session_state["profile"] = profile
        app.session_state["workspace_page"] = "Transactions"
        for step in WORKFLOW_STATE_KEYS:
            app.session_state[step] = True

        app.run()

        saved_profile = app.session_state["profile"]
        self.assertEqual(saved_profile["vault_balance"], 17_000)
        self.assertEqual(len(saved_profile["transactions"]), 1)
        self.assertEqual(saved_profile["transactions"][0]["type"], "Scheduled payout")
        self.assertFalse(app.exception)

    def test_deposit_records_initial_balance_and_transaction(self) -> None:
        profile = {
            **default_profile("Test Student"),
            "daily_food": 1_000,
            "total_funds": 5_000,
        }
        app = AppTest.from_file(APP_PATH, default_timeout=10)
        app.session_state["profile"] = profile
        app.session_state["workspace_page"] = "5. Deposit money"
        for step in WORKFLOW_STATE_KEYS[:-1]:
            app.session_state[step] = True

        app.run()
        app.checkbox[0].check().run()
        submit_button = next(
            button for button in app.button if button.label == "Record simulated deposit"
        )
        submit_button.click().run()

        saved_profile = app.session_state["profile"]
        self.assertEqual(saved_profile["initial_deposit"], 5_000)
        self.assertEqual(saved_profile["vault_balance"], 5_000)
        self.assertEqual(len(saved_profile["transactions"]), 1)
        self.assertEqual(saved_profile["transactions"][0]["type"], "Deposit")
        self.assertFalse(app.exception)


if __name__ == "__main__":
    unittest.main()
