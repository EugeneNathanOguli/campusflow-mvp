from __future__ import annotations

import hmac
from pathlib import Path

import streamlit as st

from backend.domain import (
    WORKFLOW_STATE_KEYS,
    calculate_plan,
    default_profile,
    next_payout_datetime,
    payout_schedule_label,
    process_due_payouts,
)
from backend.storage import load_workspace, save_workspace
from frontend.pages import render_page


def user_key(auth_configured: bool) -> str:
    if auth_configured:
        return getattr(st.user, "sub", None) or getattr(st.user, "email", None) or "authenticated-user"
    return "demo-user"


def money(value: float) -> str:
    return f"UGX {value:,.0f}"


def render_app() -> None:
    st.set_page_config(
        page_title="CampusFlow",
        page_icon=":material/account_balance_wallet:",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    auth_settings = st.secrets.get("auth", {})
    auth_configured = bool(auth_settings.get("client_id"))

    database_path = Path(__file__).resolve().parent.parent / "campusflow.db"
    supabase_settings = st.secrets.get("supabase", {})
    supabase_url = supabase_settings.get("url", "").rstrip("/")
    supabase_service_key = supabase_settings.get("service_role_key", "")

    if auth_configured and not st.user.is_logged_in:
        st.title("Welcome to CampusFlow", icon=":material/account_balance_wallet:")
        st.write("Sign in to view your private allowance workspace.")
        st.info("Your identity provider protects access to your profile and vault information.", icon=":material/lock:")
        if st.button("Sign in", type="primary", icon=":material/login:"):
            st.login()
        st.stop()

    profile_migrated = False
    if "profile" not in st.session_state:
        saved_profile, saved_workflow = load_workspace(user_key(auth_configured), auth_configured, supabase_url, supabase_service_key, database_path)
        profile = {**default_profile(st.user.name if auth_configured and st.user.name else ""), **saved_profile}
        profile_migrated = any(
            key not in saved_profile
            for key in ("vault_balance", "initial_deposit", "transactions", "next_payout_at")
        )
        if profile["locked"] and "vault_balance" not in saved_profile:
            profile["vault_balance"] = profile["total_funds"]
        if profile["locked"] and "initial_deposit" not in saved_profile:
            profile["initial_deposit"] = profile["total_funds"]
        if profile["locked"] and profile["vault_balance"] > 0 and not profile["next_payout_at"]:
            profile["next_payout_at"] = next_payout_datetime(profile).isoformat()
        st.session_state.profile = profile
        for workflow_step in WORKFLOW_STATE_KEYS:
            st.session_state[workflow_step] = saved_workflow.get(workflow_step, False)

    profile = st.session_state.profile
    old_balance = profile["vault_balance"]
    old_next_payout_at = profile["next_payout_at"]
    due_transactions = process_due_payouts(profile)
    if (
        due_transactions
        or profile_migrated
        or profile["vault_balance"] != old_balance
        or profile["next_payout_at"] != old_next_payout_at
    ):
        save_workspace(
            user_key(auth_configured),
            profile,
            {step: st.session_state.get(step, False) for step in WORKFLOW_STATE_KEYS},
            auth_configured,
            supabase_url,
            supabase_service_key,
            database_path,
        )
    if due_transactions:
        st.toast(
            f"{len(due_transactions)} simulated scheduled payout(s) recorded.",
            icon=":material/check_circle:",
        )

    if "approved" not in st.session_state:
        st.session_state.approved = False

    if "admin_authenticated" not in st.session_state:
        st.session_state.admin_authenticated = False

    for workflow_step in WORKFLOW_STATE_KEYS:
        st.session_state.setdefault(workflow_step, False)

    admin_passcode = st.secrets.get("admin_passcode", "")
    admin_access_enabled = bool(admin_passcode)

    available_funds = (
        profile["vault_balance"] if profile["locked"] else profile["total_funds"]
    )
    plan = calculate_plan(
        available_funds,
        profile["duration_weeks"],
        profile["daily_food"],
        profile["daily_other"],
        profile["fixed_weekly"],
        profile["payout_frequency"],
    )

    if "review_queue" not in st.session_state:
        st.session_state.review_queue = [
            {"Student": profile["name"] or "New student", "Network": profile["network"], "Phone": profile["phone"] or "Not provided", "Amount": money(plan["payout_amount"]), "Status": "Ready", "Reason": "No issues detected."},
            {"Student": "Joel M.", "Network": "Airtel", "Phone": "0701 883 214", "Amount": "UGX 175,000", "Status": "Ready", "Reason": "No issues detected."},
            {"Student": "Nabirye S.", "Network": "MTN", "Phone": "0774 102 665", "Amount": "UGX 210,000", "Status": "Needs review", "Reason": "Manual check required: phone number and payout amount need confirmation before release."},
            {"Student": "David O.", "Network": "Airtel", "Phone": "0755 430 118", "Amount": "UGX 160,000", "Status": "Ready", "Reason": "No issues detected."},
        ]

    with st.sidebar:
        st.markdown("# campusflow")
        st.badge("Student allowance planner", icon=":material/account_balance_wallet:", color="orange")
        st.caption("Your allowance, paced with purpose.")
        st.space("small")
        if admin_access_enabled:
            with st.expander("Admin access", icon=":material/lock:"):
                with st.form("admin_login"):
                    entered_passcode = st.text_input("Admin passcode", type="password")
                    admin_login = st.form_submit_button("Sign in", icon=":material/login:")
                if admin_login:
                    st.session_state.admin_authenticated = hmac.compare_digest(entered_passcode, admin_passcode)
                    if st.session_state.admin_authenticated:
                        st.success("Admin access granted", icon=":material/check_circle:")
                    else:
                        st.error("Incorrect passcode", icon=":material/error:")

        workspace_options = [
            "Welcome",
            "Overview",
            "1. Sign up",
            "2. Expenses",
            "3. Calculate plan",
            "4. Payout schedule",
            "5. Deposit money",
            "Transactions",
            "Emergency withdrawal",
        ]
        if admin_access_enabled and st.session_state.admin_authenticated:
            workspace_options.append("Admin desk")
        if "workspace_page" not in st.session_state:
            st.session_state.workspace_page = "Welcome" if not st.session_state.signup_complete else "Overview"
        page = st.segmented_control(
            "Workspace",
            workspace_options,
            default=st.session_state.workspace_page,
            label_visibility="collapsed",
        )
        st.session_state.workspace_page = page
        completed_steps = sum(
            st.session_state[workflow_step]
            for workflow_step in (
                "signup_complete",
                "expenses_complete",
                "plan_complete",
                "schedule_complete",
                "deposit_complete",
            )
        )
        st.progress(completed_steps / 5, text=f"Setup progress: {completed_steps} of 5 steps")
        for step_number, (step_label, workflow_step) in enumerate(
            zip(
                ("Sign up", "Expenses", "Calculate plan", "Payout schedule", "Deposit money"),
                ("signup_complete", "expenses_complete", "plan_complete", "schedule_complete", "deposit_complete"),
            ),
            start=1,
        ):
            marker = ":material/check_circle:" if st.session_state[workflow_step] else ":material/radio_button_unchecked:"
            st.caption(f"{marker} {step_number}. {step_label}")
        st.space("large")
        st.caption("Signed in as")
        st.markdown(f"**{profile['name']}**")
        st.caption(f"{profile['network']} · {profile['phone']}")
        st.metric("Simulated vault balance", money(profile["vault_balance"]))
        if auth_configured:
            st.caption(st.user.email or "Verified account")
            if st.button("Sign out", icon=":material/logout:"):
                st.logout()
        st.space("large")
        if auth_configured:
            st.badge("Private workspace", icon=":material/lock:", color="green")
        else:
            st.badge("Demo workspace", icon=":material/science:", color="blue")
            st.caption("No identity provider is configured. This mode uses sample data only.")
        st.caption("Payouts are simulated. No real money is moved.")

    required_steps = {
        "2. Expenses": (("signup_complete", "Sign up"),),
        "3. Calculate plan": (("signup_complete", "Sign up"), ("expenses_complete", "Expenses")),
        "4. Payout schedule": (("signup_complete", "Sign up"), ("expenses_complete", "Expenses"), ("plan_complete", "Calculate plan")),
        "5. Deposit money": (("signup_complete", "Sign up"), ("expenses_complete", "Expenses"), ("plan_complete", "Calculate plan"), ("schedule_complete", "Payout schedule")),
        "Transactions": (("signup_complete", "Sign up"),),
        "Emergency withdrawal": (("signup_complete", "Sign up"),),
    }
    if page in required_steps:
        missing_steps = [label for step, label in required_steps[page] if not st.session_state[step]]
        if missing_steps:
            st.warning(f"Complete {', '.join(missing_steps)} before continuing.", icon=":material/arrow_back:")
            st.stop()

    render_page(page, profile, auth_configured, supabase_url, supabase_service_key, database_path, user_key(auth_configured), money, plan)
