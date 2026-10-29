from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

WORKFLOW_STATE_KEYS = (
    "signup_complete",
    "expenses_complete",
    "plan_complete",
    "schedule_complete",
    "deposit_complete",
)


def default_profile(user_name: str = "") -> dict:
    return {
        "name": user_name,
        "phone": "",
        "network": "MTN",
        "daily_food": 0,
        "daily_other": 0,
        "fixed_weekly": 0,
        "total_funds": 0,
        "duration_weeks": 4,
        "mode": "Fixed cash",
        "payout_frequency": "Weekly",
        "deposit_day": "Monday",
        "deposit_time": "07:00",
        "deposit_day_of_month": 1,
        "locked": False,
        "vault_balance": 0,
        "initial_deposit": 0,
        "transactions": [],
        "next_payout_at": None,
    }


def normalize_uganda_phone(phone: str) -> str | None:
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("256"):
        digits = "0" + digits[3:]
    if len(digits) != 10 or not digits.startswith("07"):
        return None
    if digits[2] not in "0123456789":
        return None
    return f"+256{digits[1:]}"


def calculate_plan(
    total_funds: float,
    duration_weeks: int,
    daily_food: float,
    daily_other: float,
    fixed_weekly: float = 0,
    payout_frequency: str = "Weekly",
) -> dict:
    daily_baseline = daily_food + daily_other + (fixed_weekly / 7)
    duration_days = duration_weeks * 7
    safe_weekly_drop = daily_baseline * 7
    payout_amount = {
        "Daily": daily_baseline,
        "Weekly": safe_weekly_drop,
        "Monthly": daily_baseline * 30,
    }[payout_frequency]
    coverage_days = total_funds / daily_baseline if daily_baseline else 0
    return {
        "daily_baseline": daily_baseline,
        "duration_days": duration_days,
        "safe_weekly_drop": safe_weekly_drop,
        "payout_amount": payout_amount,
        "coverage_days": coverage_days,
        "required_deposit": safe_weekly_drop * duration_weeks,
    }


def next_payout_date(current_profile: dict, now: datetime | None = None) -> date:
    return next_payout_datetime(current_profile, now).date()


def next_payout_datetime(current_profile: dict, now: datetime | None = None) -> datetime:
    kampala = ZoneInfo("Africa/Kampala")
    current_time = now or datetime.now(kampala)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=kampala)
    else:
        current_time = current_time.astimezone(kampala)

    payout_time = time.fromisoformat(current_profile["deposit_time"])
    frequency = current_profile["payout_frequency"]
    today = current_time.date()

    if frequency == "Daily":
        payout_date = today
        if datetime.combine(payout_date, payout_time, tzinfo=kampala) <= current_time:
            payout_date += timedelta(days=1)
    elif frequency == "Weekly":
        weekdays = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
        target_weekday = weekdays.index(current_profile["deposit_day"])
        days_until_payout = (target_weekday - today.weekday()) % 7
        payout_date = today + timedelta(days=days_until_payout)
        if datetime.combine(payout_date, payout_time, tzinfo=kampala) <= current_time:
            payout_date += timedelta(days=7)
    elif frequency == "Monthly":
        payout_day = int(current_profile["deposit_day_of_month"])
        if not 1 <= payout_day <= 28:
            raise ValueError("Monthly payout day must be between 1 and 28.")
        payout_date = date(today.year, today.month, payout_day)
        if datetime.combine(payout_date, payout_time, tzinfo=kampala) <= current_time:
            next_month = today.month % 12 + 1
            next_year = today.year + (today.month == 12)
            payout_date = date(next_year, next_month, payout_day)
    else:
        raise ValueError(f"Unsupported payout frequency: {frequency}")

    return datetime.combine(payout_date, payout_time, tzinfo=kampala)


def make_transaction(
    transaction_type: str,
    amount: float,
    balance_after: float,
    description: str,
    occurred_at: datetime | None = None,
) -> dict:
    timestamp = occurred_at or datetime.now(ZoneInfo("Africa/Kampala"))
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=ZoneInfo("Africa/Kampala"))
    else:
        timestamp = timestamp.astimezone(ZoneInfo("Africa/Kampala"))
    return {
        "id": uuid4().hex,
        "type": transaction_type,
        "amount": round(amount),
        "balance_after": round(balance_after),
        "description": description,
        "timestamp": timestamp.isoformat(),
    }


def process_due_payouts(
    current_profile: dict,
    now: datetime | None = None,
) -> list[dict]:
    if not current_profile.get("locked"):
        return []

    kampala = ZoneInfo("Africa/Kampala")
    current_time = now or datetime.now(kampala)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=kampala)
    else:
        current_time = current_time.astimezone(kampala)

    next_payout_at = current_profile.get("next_payout_at")
    if next_payout_at is None:
        next_due = next_payout_datetime(current_profile, current_time)
    else:
        next_due = datetime.fromisoformat(next_payout_at)
        if next_due.tzinfo is None:
            next_due = next_due.replace(tzinfo=kampala)
        else:
            next_due = next_due.astimezone(kampala)

    balance = max(0, round(current_profile.get("vault_balance", 0)))
    payout_plan = calculate_plan(
        balance,
        current_profile["duration_weeks"],
        current_profile["daily_food"],
        current_profile["daily_other"],
        current_profile["fixed_weekly"],
        current_profile["payout_frequency"],
    )
    daily_baseline = payout_plan["daily_baseline"]
    payout_amount = (
        max(1, round(payout_plan["payout_amount"]))
        if daily_baseline > 0
        else 0
    )
    new_transactions = []

    if payout_amount == 0 and next_due <= current_time:
        next_due = next_payout_datetime(current_profile, current_time)

    while next_due <= current_time and balance > 0 and payout_amount > 0:
        actual_amount = min(balance, payout_amount)
        balance -= actual_amount
        transaction = make_transaction(
            "Scheduled payout",
            actual_amount,
            balance,
            "Simulated scheduled payout",
            next_due,
        )
        current_profile.setdefault("transactions", []).append(transaction)
        new_transactions.append(transaction)
        next_due = next_payout_datetime(current_profile, next_due)

    current_profile["vault_balance"] = balance
    current_profile["next_payout_at"] = (
        next_due.isoformat() if balance > 0 else None
    )
    return new_transactions


def time_greeting() -> str:
    current_hour = datetime.now(ZoneInfo("Africa/Kampala")).hour
    if current_hour < 12:
        return "Good morning"
    if current_hour < 18:
        return "Good afternoon"
    return "Good evening"


def payout_schedule_label(current_profile: dict) -> str:
    frequency = current_profile["payout_frequency"]
    if frequency == "Daily":
        return f"Every day at {current_profile['deposit_time']} EAT"
    if frequency == "Monthly":
        return f"Monthly on day {current_profile['deposit_day_of_month']} at {current_profile['deposit_time']} EAT"
    return f"Every {current_profile['deposit_day']} at {current_profile['deposit_time']} EAT"
