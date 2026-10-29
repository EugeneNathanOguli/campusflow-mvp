from __future__ import annotations

from datetime import date, timedelta

import streamlit as st

from backend.domain import (
    WORKFLOW_STATE_KEYS,
    calculate_plan,
    make_transaction,
    next_payout_datetime,
    next_payout_date,
    normalize_uganda_phone,
    payout_schedule_label,
    time_greeting,
)
from backend.storage import save_workspace


def render_welcome_page(auth_configured: bool) -> None:
    st.badge("A calmer way to manage student money", icon=":material/auto_awesome:", color="orange")
    st.title("Welcome to CampusFlow", icon=":material/account_balance_wallet:")
    st.subheader("Make your allowance last with a plan that fits your life.")
    st.write("CampusFlow helps you understand your everyday costs, choose how long your money should last, and receive deposits on a schedule that works for you.")

    with st.container(horizontal=True, gap="medium"):
        with st.container(border=True):
            st.subheader("Know your number", icon=":material/insights:")
            st.caption("See what your daily life really costs.")
        with st.container(border=True):
            st.subheader("Choose your pace", icon=":material/tune:")
            st.caption("Plan daily, weekly, or monthly deposits.")
        with st.container(border=True):
            st.subheader("Keep your essentials covered", icon=":material/shield:")
            st.caption("Give your allowance a clear purpose.")

    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.subheader("A plan built around you", icon=":material/route:")
            st.write("Build your expense baseline, calculate the right allowance amount, choose your payout rhythm, and review everything before you deposit.")
    with right:
        with st.container(border=True):
            st.subheader("Your five-step journey", icon=":material/checklist:")
            st.markdown("**1** Create your account  \n**2** Add your expenses  \n**3** Calculate your plan  \n**4** Choose your payout schedule  \n**5** Deposit your allowance")

    st.space("small")
    with st.container(horizontal=True, vertical_alignment="center"):
        if st.button("Start your journey", type="primary", icon=":material/arrow_forward:"):
            st.session_state.workspace_page = "1. Sign up"
            st.rerun()
        st.caption("Takes about two minutes to set up")
    if auth_configured:
        st.caption("Already have an account?")
        if st.button("Sign in", icon=":material/login:"):
            st.login()


def render_signup_page(
    profile: dict,
    auth_configured: bool,
    supabase_url: str,
    supabase_service_key: str,
    database_path,
    user_key: str,
) -> None:
    st.title("Create your CampusFlow account", icon=":material/person_add:")
    st.write("Start with the account that will receive your scheduled allowance.")
    with st.form("student_signup"):
        name = st.text_input("Your name", value=profile["name"], placeholder="Enter your name")
        network = st.selectbox("Mobile Money network", ["MTN", "Airtel"], index=["MTN", "Airtel"].index(profile["network"]))
        phone = st.text_input("Registered phone number", value=profile["phone"], placeholder="Enter your phone number")
        submitted = st.form_submit_button("Save account details", type="primary", icon=":material/check:")
    if submitted:
        normalized_phone = normalize_uganda_phone(phone)
        if not name.strip():
            st.error("Enter your name before continuing.", icon=":material/error:")
        elif not normalized_phone:
            st.error("Enter a valid Ugandan mobile number, for example 0772 123 456.", icon=":material/error:")
        else:
            profile.update({"name": name.strip(), "network": network, "phone": normalized_phone})
            st.session_state.signup_complete = True
            save_workspace(user_key, profile, {step: st.session_state[step] for step in WORKFLOW_STATE_KEYS}, auth_configured, supabase_url, supabase_service_key, database_path)
            st.session_state.workspace_page = "2. Expenses"
            st.toast("Account details saved", icon=":material/check_circle:")
            st.rerun()


def render_expenses_page(
    profile: dict,
    auth_configured: bool,
    supabase_url: str,
    supabase_service_key: str,
    database_path,
    user_key: str,
    money,
) -> None:
    st.title("Your everyday expenses", icon=":material/receipt_long:")
    st.write("Tell us what it costs to get through a normal week, including expenses that do not happen every day.")
    with st.form("student_expenses"):
        daily_food = st.number_input("Daily food budget (UGX)", min_value=0, value=profile["daily_food"], step=1000)
        daily_other = st.number_input("Daily transport, airtime and printing (UGX)", min_value=0, value=profile["daily_other"], step=1000)
        fixed_weekly = st.number_input("Fixed weekly expenses (UGX)", min_value=0, value=profile["fixed_weekly"], step=5000, help="For rent, subscriptions, or other costs you pay once a week or less often.")
        submitted = st.form_submit_button("Save expense baseline", type="primary", icon=":material/save:")
    if submitted:
        if daily_food + daily_other + fixed_weekly <= 0:
            st.error("Enter at least one expense greater than zero before continuing.", icon=":material/error:")
        else:
            profile.update({"daily_food": daily_food, "daily_other": daily_other, "fixed_weekly": fixed_weekly})
            st.session_state.expenses_complete = True
            save_workspace(user_key, profile, {step: st.session_state[step] for step in WORKFLOW_STATE_KEYS}, auth_configured, supabase_url, supabase_service_key, database_path)
            st.session_state.workspace_page = "3. Calculate plan"
            st.toast("Expense baseline saved", icon=":material/check_circle:")
            st.rerun()
    st.info(f"Your current daily baseline is **{money(profile['daily_food'] + profile['daily_other'] + profile['fixed_weekly'] / 7)}** including fixed expenses.", icon=":material/insights:")


def render_plan_page(
    profile: dict,
    auth_configured: bool,
    supabase_url: str,
    supabase_service_key: str,
    database_path,
    user_key: str,
    money,
) -> None:
    st.title("Calculate your allowance plan", icon=":material/calculate:")
    st.write("Choose the amount of money you have or how long you need it to last, and CampusFlow will suggest a realistic allowance plan.")
    if profile["daily_food"] + profile["daily_other"] + profile["fixed_weekly"] / 7 <= 0:
        st.warning("Add at least one expense greater than zero before calculating your plan.", icon=":material/arrow_back:")
        return

    modes = ["How much cash I have", "How long I need it to last"]
    mode = st.segmented_control(
        "I know",
        modes,
        default=profile["mode"] if profile["mode"] in modes else modes[0],
    )
    if mode == "How much cash I have":
        total_funds = st.number_input(
            "Available allowance (UGX)",
            min_value=0,
            value=profile["vault_balance"] if profile["locked"] else profile["total_funds"],
            step=50_000,
        )
        duration_weeks = profile["duration_weeks"]
        st.caption("CampusFlow will calculate how many days this allowance can cover.")
    else:
        duration_weeks = st.slider("Target duration (weeks)", min_value=4, max_value=20, value=profile["duration_weeks"])
        total_funds = st.number_input(
            "Allowance currently available (UGX)",
            min_value=0,
            value=profile["vault_balance"] if profile["locked"] else profile["total_funds"],
            step=50_000,
        )
        st.caption("CampusFlow will calculate the target and compare it with your available allowance.")

    preview = calculate_plan(total_funds, duration_weeks, profile["daily_food"], profile["daily_other"], profile["fixed_weekly"], profile["payout_frequency"])
    st.subheader("Your result", divider="gray")
    c1, c2, c3 = st.columns(3)
    c1.metric("Daily baseline", money(preview["daily_baseline"]), border=True)
    c2.metric(f"{profile['payout_frequency']} payout", money(preview["payout_amount"]), border=True)
    if mode == "How long I need it to last":
        c3.metric("Target coverage", f"{preview['duration_days']} days", border=True)
        shortfall = max(preview["required_deposit"] - total_funds, 0)
        st.success(f"You need **{money(preview['required_deposit'])}** to cover {duration_weeks} weeks.", icon=":material/lightbulb:")
        st.metric("Additional amount needed", money(shortfall), border=True)
    else:
        c3.metric("Projected coverage", f"{preview['coverage_days']:.0f} days", border=True)
        st.success(f"Your allowance can cover approximately **{preview['coverage_days']:.0f} days**.", icon=":material/lightbulb:")
        st.metric("Recommended for selected duration", money(preview["required_deposit"]), border=True)
    can_save_plan = mode == "How long I need it to last" or total_funds > 0
    if st.button("Save this plan", type="primary", icon=":material/lock:", disabled=not can_save_plan):
        profile.update({
            "total_funds": total_funds,
            "duration_weeks": duration_weeks,
            "mode": mode,
        })
        st.session_state.plan_complete = True
        save_workspace(user_key, profile, {step: st.session_state[step] for step in WORKFLOW_STATE_KEYS}, auth_configured, supabase_url, supabase_service_key, database_path)
        st.session_state.workspace_page = "4. Payout schedule"
        st.toast("Plan saved", icon=":material/check_circle:")
        st.rerun()


def render_schedule_page(
    profile: dict,
    auth_configured: bool,
    supabase_url: str,
    supabase_service_key: str,
    database_path,
    user_key: str,
) -> None:
    st.title("Choose your payout schedule", icon=":material/event:")
    st.write("Choose how often money should be deposited into your account.")
    with st.form("payout_schedule"):
        payout_frequency = st.selectbox("Deposit frequency", ["Daily", "Weekly", "Monthly"], index=["Daily", "Weekly", "Monthly"].index(profile["payout_frequency"]))
        if payout_frequency == "Weekly":
            deposit_day = st.selectbox("Deposit day", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"], index=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"].index(profile["deposit_day"]))
            deposit_day_of_month = profile["deposit_day_of_month"]
        elif payout_frequency == "Monthly":
            deposit_day = profile["deposit_day"]
            deposit_day_of_month = st.number_input("Day of the month", min_value=1, max_value=28, value=profile["deposit_day_of_month"], step=1, help="Choose up to day 28 so every month has a valid payout date.")
        else:
            deposit_day = profile["deposit_day"]
            deposit_day_of_month = profile["deposit_day_of_month"]
        deposit_time = st.selectbox("Deposit time", ["06:00", "07:00", "08:00", "12:00", "18:00"], index=["06:00", "07:00", "08:00", "12:00", "18:00"].index(profile["deposit_time"]))
        submitted = st.form_submit_button("Save payout schedule", type="primary", icon=":material/schedule:")
    if submitted:
        profile.update({"payout_frequency": payout_frequency, "deposit_day": deposit_day, "deposit_time": deposit_time, "deposit_day_of_month": deposit_day_of_month})
        if profile["locked"] and profile["vault_balance"] > 0:
            profile["next_payout_at"] = next_payout_datetime(profile).isoformat()
        st.session_state.schedule_complete = True
        save_workspace(user_key, profile, {step: st.session_state[step] for step in WORKFLOW_STATE_KEYS}, auth_configured, supabase_url, supabase_service_key, database_path)
        st.session_state.workspace_page = "5. Deposit money"
        st.toast("Payout schedule saved", icon=":material/check_circle:")
        st.rerun()
    st.info(f"Your payout will be scheduled **{payout_schedule_label(profile)}**.", icon=":material/calendar_month:")


def render_deposit_page(profile: dict, auth_configured: bool, supabase_url: str, supabase_service_key: str, database_path, user_key: str, money, plan: dict) -> None:
    st.title("Deposit your allowance", icon=":material/account_balance:")
    st.write("Review your plan, then add a simulated deposit to your CampusFlow vault.")
    if profile["locked"]:
        st.session_state.deposit_complete = True
    with st.container(border=True):
        deposit_amount = (
            profile["initial_deposit"] if profile["locked"] else profile["total_funds"]
        )
        st.metric("Amount to deposit", money(deposit_amount))
        st.metric("Current simulated balance", money(profile["vault_balance"]))
        st.write(f"**{profile['duration_weeks']} weeks** · {payout_schedule_label(profile)} · {profile['network']} {profile['phone']}")
        st.caption(f"{profile['payout_frequency']} payout: {money(plan['payout_amount'])} · Daily baseline: {money(plan['daily_baseline'])}")
    confirm_deposit = st.checkbox("I confirm that these details and the deposit amount are correct.")
    if profile["locked"]:
        st.success("Your simulated deposit has already been recorded.", icon=":material/lock:")
    else:
        if profile["total_funds"] <= 0:
            st.info("Save a plan with a positive allowance amount before recording a simulated deposit.")
    if not profile["locked"] and st.button("Record simulated deposit", type="primary", icon=":material/lock:", disabled=not confirm_deposit or profile["total_funds"] <= 0):
        profile["locked"] = True
        profile["vault_balance"] = round(profile["total_funds"])
        profile["initial_deposit"] = profile["vault_balance"]
        profile["next_payout_at"] = (
            next_payout_datetime(profile).isoformat()
            if profile["vault_balance"] > 0
            else None
        )
        profile.setdefault("transactions", []).append(
            make_transaction(
                "Deposit",
                profile["vault_balance"],
                profile["vault_balance"],
                "Simulated allowance deposit",
            )
        )
        st.session_state.deposit_complete = True
        save_workspace(user_key, profile, {step: st.session_state[step] for step in WORKFLOW_STATE_KEYS}, auth_configured, supabase_url, supabase_service_key, database_path)
        st.session_state.workspace_page = "Overview"
        st.success("Deposit recorded. Payout dispatch is simulated in this prototype.", icon=":material/check_circle:")
        st.rerun()


def render_transactions_page(profile: dict, money) -> None:
    st.title("Transactions", icon=":material/receipt_long:")
    st.caption("Simulated deposits, scheduled payouts, and withdrawals recorded for this workspace.")
    st.metric("Current simulated balance", money(profile["vault_balance"]))
    transactions = sorted(
        profile.get("transactions", []),
        key=lambda transaction: transaction["timestamp"],
        reverse=True,
    )
    if transactions:
        st.dataframe(
            [
                {
                    "Date (EAT)": transaction["timestamp"],
                    "Type": transaction["type"],
                    "Amount": money(transaction["amount"]),
                    "Balance after": money(transaction["balance_after"]),
                    "Description": transaction["description"],
                }
                for transaction in transactions
            ],
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("No transactions yet. A transaction will appear here after you record a simulated deposit.")


def render_emergency_withdrawal_page(
    profile: dict,
    auth_configured: bool,
    supabase_url: str,
    supabase_service_key: str,
    database_path,
    user_key: str,
    money,
) -> None:
    st.title("Emergency withdrawal", icon=":material/emergency:")
    st.write("Request a simulated withdrawal from your available vault balance. No money is transferred.")
    balance = max(0, round(profile["vault_balance"]))
    st.metric("Available simulated balance", money(balance))
    if not profile["locked"] or balance <= 0:
        st.info("A simulated deposit with a positive balance is required before requesting a withdrawal.")
        return

    with st.form("emergency_withdrawal"):
        amount = st.number_input(
            "Withdrawal amount (UGX)",
            min_value=1,
            max_value=balance,
            value=min(balance, 10_000),
            step=1_000,
        )
        reason = st.selectbox(
            "Reason",
            ["Medical costs", "Urgent travel", "Essential supplies", "Other"],
        )
        details = st.text_area("Additional details (optional)", max_chars=500)
        submitted = st.form_submit_button(
            "Record simulated withdrawal",
            type="primary",
            icon=":material/outbound:",
        )

    if submitted:
        if amount <= 0 or amount > balance:
            st.error("Enter an amount within your available simulated balance.")
            return
        profile["vault_balance"] = balance - amount
        if profile["vault_balance"] == 0:
            profile["next_payout_at"] = None
        description = reason if not details.strip() else f"{reason}: {details.strip()}"
        profile.setdefault("transactions", []).append(
            make_transaction(
                "Emergency withdrawal",
                amount,
                profile["vault_balance"],
                description,
            )
        )
        save_workspace(
            user_key,
            profile,
            {step: st.session_state[step] for step in WORKFLOW_STATE_KEYS},
            auth_configured,
            supabase_url,
            supabase_service_key,
            database_path,
        )
        st.toast("Simulated withdrawal recorded", icon=":material/check_circle:")
        st.rerun()


def render_admin_page(profile: dict, money) -> None:
    st.title("Admin desk", icon=":material/verified_user:")
    st.write("Review the next payout batch, reconcile the vault ledger, and release approved drops.")

    k1, k2, k3 = st.columns(3)
    k1.metric("Students covered", "128", "+14 this week", border=True)
    k2.metric("Next payout batch", money(1840000), "24 students", border=True)
    k3.metric("Ledger match", "99.8%", "Reconciled today", border=True)

    st.subheader("Monday payout queue", divider="gray")
    rows = st.session_state.review_queue
    for index, row in enumerate(rows):
        if row["Status"] == "Needs review":
            with st.container(border=True):
                st.write(f"**{row['Student']}**")
                st.caption(f"{row['Network']} · {row['Phone']} · {row['Amount']}")
                st.warning(f"Review reason: {row['Reason']}", icon=":material/report_problem:")
                review_col_1, review_col_2 = st.columns(2)
                if review_col_1.button("Approve payout", key=f"approve_{index}", type="primary"):
                    row["Status"] = "Approved"
                    row["Reason"] = "Approved after manual review."
                    st.toast(f"{row['Student']} approved for payout", icon=":material/check_circle:")
                    st.rerun()
                if review_col_2.button("Reject payout", key=f"reject_{index}"):
                    row["Status"] = "Rejected"
                    row["Reason"] = "Rejected after manual review."
                    st.toast(f"{row['Student']} rejected from payout", icon=":material/close:")
                    st.rerun()
                st.markdown("---")

    st.dataframe(rows, width="stretch", hide_index=True, column_config={"Status": st.column_config.TextColumn("Status")})
    st.caption(f"Next scheduled release: {payout_schedule_label(profile)}")
    if not st.session_state.approved:
        if st.button("Approve ready payouts", type="primary", icon=":material/send:"):
            st.session_state.approved = True
            st.toast("Payout batch approved for dispatch", icon=":material/check_circle:")
    else:
        st.success("Ready payouts approved. Dispatch is simulated in this prototype.", icon=":material/check_circle:")


def render_overview_page(profile: dict, plan: dict, money) -> None:
    first_name = profile["name"].split()[0] if profile["name"].strip() else "there"
    st.title(f"{time_greeting()}, {first_name}", icon=":material/waving_hand:")
    st.write("Your essentials are paced. You can make today’s choices with a little more room to breathe.")

    with st.container(border=True):
        st.subheader("Your allowance snapshot", icon=":material/insights:")
        st.metric("Vault balance", money(profile["vault_balance"]), "Simulated available balance", border=True)
        st.metric(f"{profile['payout_frequency']} payout", money(plan["payout_amount"]), payout_schedule_label(profile), border=True)
        st.metric("Daily target", money(plan["daily_baseline"]), "Food + essentials", border=True)

    st.space("small")
    st.subheader("Manage your plan", icon=":material/edit:")
    st.caption("Update your details at any time. Your saved progress and existing plan data will stay intact.")
    with st.container(horizontal=True, wrap=True):
        if st.button("Edit account details", icon=":material/person:"):
            st.session_state.workspace_page = "1. Sign up"
            st.rerun()
        if st.button("Edit expenses", icon=":material/receipt_long:"):
            st.session_state.workspace_page = "2. Expenses"
            st.rerun()
        if st.button("Edit allowance plan", icon=":material/calculate:"):
            st.session_state.workspace_page = "3. Calculate plan"
            st.rerun()
        if st.button("Edit payout schedule", icon=":material/schedule:"):
            st.session_state.workspace_page = "4. Payout schedule"
            st.rerun()

    st.space("small")
    left, right = st.columns([1.35, 1])
    with left:
        with st.container(border=True):
            st.subheader("Allowance coverage", icon=":material/shield:")
            if plan["daily_baseline"] <= 0:
                st.info("Add an expense baseline to estimate your allowance coverage.")
            else:
                if profile["locked"]:
                    st.badge("Secured in demo", icon=":material/check_circle:", color="green")
                else:
                    st.badge("Ready to deposit", icon=":material/pending:", color="blue")
                st.markdown(f"### Covered through {(date.today() + timedelta(days=int(plan['coverage_days']))).strftime('%d %b %Y')}")
                st.progress(min(plan["coverage_days"] / (profile["duration_weeks"] * 7), 1.0))
                st.caption(f"{plan['coverage_days']:.0f} days of estimated baseline cover")

        with st.container(border=True):
            st.subheader("Next scheduled payout", icon=":material/event:")
            drop_date = next_payout_date(profile)
            st.markdown(f"### {drop_date.strftime('%A, %d %B')}")
            st.write(f"**{money(plan['payout_amount'])}** to {profile['network']} · {profile['phone']}")
            st.caption(f"Planned for {payout_schedule_label(profile)}. This is a schedule preview; payouts and SMS are not sent in this prototype.")

    with right:
        with st.container(border=True):
            st.subheader("Expense baseline", icon=":material/tune:")
            st.metric("Food", money(profile["daily_food"]))
            st.metric("Transport + airtime", money(profile["daily_other"]))
            st.caption("This is your recommended daily ceiling between drops.")

        with st.container(border=True):
            st.subheader("Prototype status", icon=":material/info:")
            st.caption("Deposits and payouts are simulated. No money is moved and no SMS is sent.")


def render_page(page: str, profile: dict, auth_configured: bool, supabase_url: str, supabase_service_key: str, database_path, user_key: str, money, plan: dict) -> None:
    if page == "Welcome":
        render_welcome_page(auth_configured)
    elif page == "1. Sign up":
        render_signup_page(profile, auth_configured, supabase_url, supabase_service_key, database_path, user_key)
    elif page == "2. Expenses":
        render_expenses_page(profile, auth_configured, supabase_url, supabase_service_key, database_path, user_key, money)
    elif page == "3. Calculate plan":
        render_plan_page(profile, auth_configured, supabase_url, supabase_service_key, database_path, user_key, money)
    elif page == "4. Payout schedule":
        render_schedule_page(profile, auth_configured, supabase_url, supabase_service_key, database_path, user_key)
    elif page == "5. Deposit money":
        render_deposit_page(profile, auth_configured, supabase_url, supabase_service_key, database_path, user_key, money, plan)
    elif page == "Transactions":
        render_transactions_page(profile, money)
    elif page == "Emergency withdrawal":
        render_emergency_withdrawal_page(
            profile,
            auth_configured,
            supabase_url,
            supabase_service_key,
            database_path,
            user_key,
            money,
        )
    elif page == "Admin desk":
        render_admin_page(profile, money)
    else:
        render_overview_page(profile, plan, money)
