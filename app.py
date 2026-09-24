from datetime import date, datetime, timedelta
import hmac
import json
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import streamlit as st


st.set_page_config(
    page_title="CampusFlow",
    page_icon=":material/account_balance_wallet:",
    layout="wide",
    initial_sidebar_state="expanded",
)


auth_settings = st.secrets.get("auth", {})
auth_configured = bool(auth_settings.get("client_id"))

DATABASE_PATH = Path(__file__).with_name("campusflow.db")
supabase_settings = st.secrets.get("supabase", {})
supabase_url = supabase_settings.get("url", "").rstrip("/")
supabase_service_key = supabase_settings.get("service_role_key", "")
supabase_configured = bool(supabase_url and supabase_service_key)


def user_key() -> str:
    if auth_configured:
        return getattr(st.user, "sub", None) or getattr(st.user, "email", None) or "authenticated-user"
    return "demo-user"


def default_profile() -> dict:
    return {
        "name": st.user.name if auth_configured and st.user.name else "",
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
    }


def load_workspace() -> tuple[dict, dict]:
    if not auth_configured:
        return default_profile(), {step: False for step in WORKFLOW_STATE_KEYS}
    if supabase_configured:
        query = urlencode({"user_key": f"eq.{user_key()}", "select": "profile,workflow"})
        rows = supabase_request("GET", f"workspaces?{query}")
        if not rows:
            return default_profile(), {step: False for step in WORKFLOW_STATE_KEYS}
        profile_data = rows[0]["profile"]
        workflow_data = rows[0]["workflow"]
        return (
            json.loads(profile_data) if isinstance(profile_data, str) else profile_data,
            json.loads(workflow_data) if isinstance(workflow_data, str) else workflow_data,
        )
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS workspaces (user_key TEXT PRIMARY KEY, profile TEXT NOT NULL, workflow TEXT NOT NULL)"
        )
        row = connection.execute(
            "SELECT profile, workflow FROM workspaces WHERE user_key = ?",
            (user_key(),),
        ).fetchone()
    if not row:
        return default_profile(), {step: False for step in WORKFLOW_STATE_KEYS}
    return json.loads(row[0]), json.loads(row[1])


def save_workspace() -> None:
    if not auth_configured:
        return
    payload = {
        "user_key": user_key(),
        "profile": st.session_state.profile,
        "workflow": {step: st.session_state[step] for step in WORKFLOW_STATE_KEYS},
    }
    if supabase_configured:
        supabase_request("POST", "workspaces", payload)
        return
    with sqlite3.connect(DATABASE_PATH) as connection:
        connection.execute(
            "INSERT INTO workspaces (user_key, profile, workflow) VALUES (?, ?, ?) "
            "ON CONFLICT(user_key) DO UPDATE SET profile = excluded.profile, workflow = excluded.workflow",
            (user_key(), json.dumps(payload["profile"]), json.dumps(payload["workflow"])),
        )


WORKFLOW_STATE_KEYS = ("signup_complete", "expenses_complete", "plan_complete", "schedule_complete", "deposit_complete")


def supabase_request(method: str, path: str, payload: dict | None = None) -> object:
    request = Request(
        f"{supabase_url}/rest/v1/{path}",
        method=method,
        headers={
            "apikey": supabase_service_key,
            "Authorization": f"Bearer {supabase_service_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation,resolution=merge-duplicates",
        },
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
    )
    with urlopen(request, timeout=10) as response:
        body = response.read().decode("utf-8")
    return json.loads(body) if body else None

if auth_configured and not st.user.is_logged_in:
    st.title("Welcome to CampusFlow", icon=":material/account_balance_wallet:")
    st.write("Sign in to view your private allowance workspace.")
    st.info("Your identity provider protects access to your profile and vault information.", icon=":material/lock:")
    if st.button("Sign in", type="primary", icon=":material/login:"):
        st.login()
    st.stop()


if "profile" not in st.session_state:
    saved_profile, saved_workflow = load_workspace()
    st.session_state.profile = {**default_profile(), **saved_profile}
    for workflow_step in WORKFLOW_STATE_KEYS:
        st.session_state[workflow_step] = saved_workflow.get(workflow_step, False)

if "approved" not in st.session_state:
    st.session_state.approved = False

if "admin_authenticated" not in st.session_state:
    st.session_state.admin_authenticated = False

for workflow_step in ("signup_complete", "expenses_complete", "plan_complete", "schedule_complete", "deposit_complete"):
    st.session_state.setdefault(workflow_step, False)

profile = st.session_state.profile
admin_passcode = st.secrets.get("admin_passcode", "")
admin_access_enabled = auth_configured and bool(admin_passcode)

def money(value: float) -> str:
    return f"UGX {value:,.0f}"


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


def next_monday() -> date:
    today = date.today()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


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


def advance_to(page_name: str, completed_step: str | None = None) -> None:
    st.session_state.next_workspace_page = page_name
    if completed_step:
        st.session_state[completed_step] = True


def open_next_workspace_page() -> None:
    next_page = st.session_state.pop("next_workspace_page", None)
    if next_page:
        st.session_state.workspace_page = next_page
        st.rerun()


plan = calculate_plan(
    profile["total_funds"],
    profile["duration_weeks"],
    profile["daily_food"],
    profile["daily_other"],
    profile["fixed_weekly"],
    profile["payout_frequency"],
)

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
        for workflow_step in ("signup_complete", "expenses_complete", "plan_complete", "schedule_complete", "deposit_complete")
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
}
if page in required_steps:
    missing_steps = [label for step, label in required_steps[page] if not st.session_state[step]]
    if missing_steps:
        st.warning(f"Complete {', '.join(missing_steps)} before continuing.", icon=":material/arrow_back:")
        st.stop()


if page == "Welcome":
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
        if st.button("Start your journey", type="primary", icon=":material/arrow_forward:", on_click=advance_to, args=("1. Sign up",)):
            open_next_workspace_page()
        st.caption("Takes about two minutes to set up")
    if auth_configured:
        st.caption("Already have an account?")
        if st.button("Sign in", icon=":material/login:"):
            st.login()

elif page == "1. Sign up":
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
            save_workspace()
            advance_to("2. Expenses")
            open_next_workspace_page()
            st.toast("Account details saved", icon=":material/check_circle:")

elif page == "2. Expenses":
    st.title("Your everyday expenses", icon=":material/receipt_long:")
    st.write("Tell us what it costs to get through a normal week, including expenses that do not happen every day.")
    with st.form("student_expenses"):
        daily_food = st.number_input("Daily food budget (UGX)", min_value=0, value=profile["daily_food"], step=1000)
        daily_other = st.number_input("Daily transport, airtime and printing (UGX)", min_value=0, value=profile["daily_other"], step=1000)
        fixed_weekly = st.number_input("Fixed weekly expenses (UGX)", min_value=0, value=profile["fixed_weekly"], step=5000, help="For rent, subscriptions, or other costs you pay once a week or less often.")
        submitted = st.form_submit_button("Save expense baseline", type="primary", icon=":material/save:", on_click=advance_to, args=("3. Calculate plan", "expenses_complete"))
    if submitted:
        profile.update({"daily_food": daily_food, "daily_other": daily_other, "fixed_weekly": fixed_weekly})
        st.session_state.expenses_complete = True
        save_workspace()
        open_next_workspace_page()
        st.toast("Expense baseline saved", icon=":material/check_circle:")
    st.info(f"Your current daily baseline is **{money(profile['daily_food'] + profile['daily_other'] + profile['fixed_weekly'] / 7)}** including fixed expenses.", icon=":material/insights:")

elif page == "3. Calculate plan":
    st.title("Calculate your allowance plan", icon=":material/calculate:")
    st.write("Choose what you know, and CampusFlow will calculate the other side for you.")
    mode = st.segmented_control("I know", ["How much cash I have", "How long I need it to last"], default="How much cash I have")
    if mode == "How much cash I have":
        total_funds = st.number_input("Available allowance (UGX)", min_value=0, value=profile["total_funds"], step=50000)
        duration_weeks = profile["duration_weeks"]
        st.caption("CampusFlow will calculate how many days this allowance can cover.")
    else:
        duration_weeks = st.slider("Target duration (weeks)", min_value=4, max_value=20, value=profile["duration_weeks"])
        total_funds = profile["total_funds"]
        st.caption("CampusFlow will calculate the amount needed for this duration.")

    preview = calculate_plan(total_funds, duration_weeks, profile["daily_food"], profile["daily_other"], profile["fixed_weekly"], profile["payout_frequency"])
    st.subheader("Your result", divider="gray")
    c1, c2, c3 = st.columns(3)
    c1.metric("Daily baseline", money(preview["daily_baseline"]), border=True)
    c2.metric(f"{profile['payout_frequency']} payout", money(preview["payout_amount"]), border=True)
    if mode == "How long I need it to last":
        c3.metric("Target coverage", f"{preview['duration_days']} days", border=True)
        st.success(f"You need **{money(preview['required_deposit'])}** to cover {duration_weeks} weeks.", icon=":material/lightbulb:")
    else:
        c3.metric("Projected coverage", f"{preview['coverage_days']:.0f} days", border=True)
        st.success(f"Your allowance can cover approximately **{preview['coverage_days']:.0f} days**.", icon=":material/lightbulb:")
    if st.button("Save this plan", type="primary", icon=":material/lock:", on_click=advance_to, args=("4. Payout schedule", "plan_complete")):
        profile.update({
            "total_funds": preview["required_deposit"] if mode == "How long I need it to last" else total_funds,
            "duration_weeks": duration_weeks,
            "mode": mode,
        })
        st.session_state.plan_complete = True
        save_workspace()
        open_next_workspace_page()
        st.toast("Plan saved", icon=":material/check_circle:")

elif page == "4. Payout schedule":
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
        submitted = st.form_submit_button("Save payout schedule", type="primary", icon=":material/schedule:", on_click=advance_to, args=("5. Deposit money", "schedule_complete"))
    if submitted:
        profile.update({"payout_frequency": payout_frequency, "deposit_day": deposit_day, "deposit_time": deposit_time, "deposit_day_of_month": deposit_day_of_month})
        st.session_state.schedule_complete = True
        save_workspace()
        open_next_workspace_page()
        st.toast("Payout schedule saved", icon=":material/check_circle:")
    st.info(f"Your payout will be scheduled **{payout_schedule_label(profile)}**.", icon=":material/calendar_month:")

elif page == "5. Deposit money":
    st.title("Deposit your allowance", icon=":material/account_balance:")
    st.write("Review your plan, then lock the allowance into your CampusFlow vault.")
    if profile["locked"]:
        st.session_state.deposit_complete = True
    with st.container(border=True):
        st.metric("Amount to deposit", money(profile["total_funds"]))
        st.write(f"**{profile['duration_weeks']} weeks** · {payout_schedule_label(profile)} · {profile['network']} {profile['phone']}")
        st.caption(f"{profile['payout_frequency']} payout: {money(plan['payout_amount'])} · Daily baseline: {money(plan['daily_baseline'])}")
    confirm_deposit = st.checkbox("I confirm that these details and the deposit amount are correct.")
    if profile["locked"]:
        st.success("Your allowance is already locked in the demo vault.", icon=":material/lock:")
    elif st.button("Deposit and lock allowance", type="primary", icon=":material/lock:", disabled=not confirm_deposit, on_click=advance_to, args=("Overview", "deposit_complete")):
        profile["locked"] = True
        st.session_state.deposit_complete = True
        save_workspace()
        open_next_workspace_page()
        st.success("Deposit recorded. Payout dispatch is simulated in this prototype.", icon=":material/check_circle:")

elif page == "Admin desk" and admin_access_enabled and st.session_state.admin_authenticated:
    st.title("Admin desk", icon=":material/verified_user:")
    st.write("Review the next payout batch, reconcile the vault ledger, and release approved drops.")

    k1, k2, k3 = st.columns(3)
    k1.metric("Students covered", "128", "+14 this week", border=True)
    k2.metric("Next payout batch", money(1840000), "24 students", border=True)
    k3.metric("Ledger match", "99.8%", "Reconciled today", border=True)

    st.subheader("Monday payout queue", divider="gray")
    rows = [
        {"Student": profile["name"] or "New student", "Network": profile["network"], "Phone": profile["phone"] or "Not provided", "Amount": money(plan["payout_amount"]), "Status": "Ready"},
        {"Student": "Joel M.", "Network": "Airtel", "Phone": "0701 883 214", "Amount": "UGX 175,000", "Status": "Ready"},
        {"Student": "Nabirye S.", "Network": "MTN", "Phone": "0774 102 665", "Amount": "UGX 210,000", "Status": "Needs review"},
        {"Student": "David O.", "Network": "Airtel", "Phone": "0755 430 118", "Amount": "UGX 160,000", "Status": "Ready"},
    ]
    st.dataframe(rows, width="stretch", hide_index=True, column_config={"Status": st.column_config.TextColumn("Status")})
    st.caption(f"Next scheduled release: {payout_schedule_label(profile)}")
    if not st.session_state.approved:
        if st.button("Approve ready payouts", type="primary", icon=":material/send:"):
            st.session_state.approved = True
            st.toast("Payout batch approved for dispatch", icon=":material/check_circle:")
    else:
        st.success("Ready payouts approved. Dispatch is simulated in this prototype.", icon=":material/check_circle:")

else:
    first_name = profile["name"].split()[0] if profile["name"].strip() else "there"
    st.title(f"{time_greeting()}, {first_name}", icon=":material/waving_hand:")
    st.write("Your essentials are paced. You can make today’s choices with a little more room to breathe.")

    with st.container(horizontal=True):
        st.metric("Vault balance", money(profile["total_funds"]), "Locked principal", border=True)
        st.metric(f"{profile['payout_frequency']} payout", money(plan["payout_amount"]), payout_schedule_label(profile), border=True)
        st.metric("Daily target", money(plan["daily_baseline"]), "Food + essentials", border=True)

    st.space("small")
    st.subheader("Manage your plan", icon=":material/edit:")
    st.caption("Update your details at any time. Your saved progress and existing plan data will stay intact.")
    with st.container(horizontal=True, wrap=True):
        if st.button("Edit account details", icon=":material/person:", on_click=advance_to, args=("1. Sign up",)):
            open_next_workspace_page()
        if st.button("Edit expenses", icon=":material/receipt_long:", on_click=advance_to, args=("2. Expenses",)):
            open_next_workspace_page()
        if st.button("Edit allowance plan", icon=":material/calculate:", on_click=advance_to, args=("3. Calculate plan",)):
            open_next_workspace_page()
        if st.button("Edit payout schedule", icon=":material/schedule:", on_click=advance_to, args=("4. Payout schedule",)):
            open_next_workspace_page()

    st.space("small")
    left, right = st.columns([1.35, 1])
    with left:
        with st.container(border=True):
            st.subheader("Meal guarantee status", icon=":material/shield:")
            if profile["locked"]:
                st.badge("Secured", icon=":material/check_circle:", color="green")
            else:
                st.badge("Ready to deposit", icon=":material/pending:", color="blue")
            st.markdown(f"### Covered through {(date.today() + timedelta(days=int(plan['coverage_days']))).strftime('%d %b %Y')}")
            st.progress(min(plan["coverage_days"] / (profile["duration_weeks"] * 7), 1.0))
            st.caption(f"{plan['coverage_days']:.0f} days of baseline cover · locked in your vault")

        with st.container(border=True):
            st.subheader("Your next drop", icon=":material/event:")
            drop_date = next_monday()
            st.markdown(f"### {drop_date.strftime('%A, %d %B')}")
            st.write(f"**{money(plan['payout_amount'])}** to {profile['network']} · {profile['phone']}")
            st.caption(f"Scheduled {payout_schedule_label(profile)}. You will receive an SMS when it is dispatched.")

    with right:
        with st.container(border=True):
            st.subheader("Expense baseline", icon=":material/tune:")
            st.metric("Food", money(profile["daily_food"]))
            st.metric("Transport + airtime", money(profile["daily_other"]))
            st.caption("This is your recommended daily ceiling between drops.")

        with st.container(border=True):
            st.subheader("Recent activity", icon=":material/history:")
            st.markdown(f"**{money(plan['payout_amount'])}** · {profile['payout_frequency']} payout")
            st.caption("Processed 2 days ago")
            st.markdown(f"**{money(profile['total_funds'])}** · Vault deposit")
            st.caption("Locked 14 days ago")
