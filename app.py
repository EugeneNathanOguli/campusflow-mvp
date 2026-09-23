from datetime import date, timedelta
import hmac

import streamlit as st


st.set_page_config(
    page_title="CampusFlow",
    page_icon=":material/account_balance_wallet:",
    layout="wide",
    initial_sidebar_state="expanded",
)


auth_settings = st.secrets.get("auth", {})
auth_configured = bool(auth_settings.get("client_id"))

if auth_configured and not st.user.is_logged_in:
    st.title("Welcome to CampusFlow", icon=":material/account_balance_wallet:")
    st.write("Sign in to view your private allowance workspace.")
    st.info("Your identity provider protects access to your profile and vault information.", icon=":material/lock:")
    if st.button("Sign in", type="primary", icon=":material/login:"):
        st.login()
    st.stop()


if "profile" not in st.session_state:
    st.session_state.profile = {
        "name": st.user.name if auth_configured and st.user.name else "Amara K.",
        "phone": "0782 456 890",
        "network": "MTN",
        "daily_food": 18000,
        "daily_other": 7000,
        "total_funds": 2100000,
        "duration_weeks": 12,
        "mode": "Fixed cash",
        "locked": True,
    }

if "approved" not in st.session_state:
    st.session_state.approved = False

if "admin_authenticated" not in st.session_state:
    st.session_state.admin_authenticated = False

profile = st.session_state.profile
admin_passcode = st.secrets.get("admin_passcode", "")

def money(value: float) -> str:
    return f"UGX {value:,.0f}"


def calculate_plan(total_funds: float, duration_weeks: int, daily_food: float, daily_other: float) -> dict:
    daily_baseline = daily_food + daily_other
    duration_days = duration_weeks * 7
    safe_weekly_drop = daily_baseline * 7
    coverage_days = total_funds / daily_baseline if daily_baseline else 0
    return {
        "daily_baseline": daily_baseline,
        "duration_days": duration_days,
        "safe_weekly_drop": safe_weekly_drop,
        "coverage_days": coverage_days,
        "required_deposit": safe_weekly_drop * duration_weeks,
    }


def next_monday() -> date:
    today = date.today()
    return today + timedelta(days=(7 - today.weekday()) % 7 or 7)


plan = calculate_plan(
    profile["total_funds"],
    profile["duration_weeks"],
    profile["daily_food"],
    profile["daily_other"],
)

with st.sidebar:
    st.markdown("# campusflow")
    st.caption("Your allowance, paced with purpose.")
    st.space("small")
    with st.expander("Admin access", icon=":material/lock:"):
        if not admin_passcode:
            st.warning("Admin access is not configured. Add an admin passcode to Streamlit secrets.", icon=":material/warning:")
        else:
            with st.form("admin_login"):
                entered_passcode = st.text_input("Admin passcode", type="password")
                admin_login = st.form_submit_button("Sign in", icon=":material/login:")
            if admin_login:
                st.session_state.admin_authenticated = hmac.compare_digest(entered_passcode, admin_passcode)
                if st.session_state.admin_authenticated:
                    st.success("Admin access granted", icon=":material/check_circle:")
                else:
                    st.error("Incorrect passcode", icon=":material/error:")

    workspace_options = ["Overview", "Plan a vault"]
    if st.session_state.admin_authenticated:
        workspace_options.append("Admin desk")
    page = st.segmented_control(
        "Workspace",
        workspace_options,
        default="Overview",
        label_visibility="collapsed",
    )
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


if page == "Plan a vault":
    st.title("Plan a vault", icon=":material/calculate:")
    st.write("Build a payout plan around the cost of staying well, not the temptation of a lump sum.")

    with st.form("vault_plan"):
        left, right = st.columns(2)
        with left:
            name = st.text_input("Your name", value=profile["name"])
            network = st.selectbox("Mobile Money network", ["MTN", "Airtel"], index=["MTN", "Airtel"].index(profile["network"]))
            phone = st.text_input("Registered phone number", value=profile["phone"])
            mode = st.segmented_control("Planning mode", ["Fixed cash", "Fixed duration"], default=profile["mode"])
        with right:
            daily_food = st.number_input("Daily food budget (UGX)", min_value=0, value=profile["daily_food"], step=1000)
            daily_other = st.number_input("Daily transport, airtime & printing (UGX)", min_value=0, value=profile["daily_other"], step=1000)
            if mode == "Fixed cash":
                total_funds = st.number_input("Available allowance (UGX)", min_value=0, value=profile["total_funds"], step=50000)
                duration_weeks = st.slider("Target coverage", min_value=4, max_value=20, value=profile["duration_weeks"])
            else:
                duration_weeks = st.slider("Target duration (weeks)", min_value=4, max_value=20, value=profile["duration_weeks"])
                total_funds = st.number_input("Starting allowance (UGX)", min_value=0, value=profile["total_funds"], step=50000)
        submitted = st.form_submit_button("Save plan", type="primary", icon=":material/lock:")

    preview = calculate_plan(total_funds, duration_weeks, daily_food, daily_other)
    st.subheader("Plan preview", divider="gray")
    c1, c2, c3 = st.columns(3)
    c1.metric("Daily baseline", money(preview["daily_baseline"]), border=True)
    c2.metric("Weekly drop", money(preview["safe_weekly_drop"]), border=True)
    c3.metric("Projected coverage", f"{preview['coverage_days']:.0f} days", border=True)

    if mode == "Fixed duration":
        st.info(f"To cover {duration_weeks} weeks at this baseline, the recommended deposit is **{money(preview['required_deposit'])}**.", icon=":material/lightbulb:")
    else:
        st.info(f"Your allowance supports approximately **{preview['coverage_days']:.0f} days** of baseline spending at this drop size.", icon=":material/lightbulb:")

    if submitted:
        st.session_state.profile = {
            "name": name,
            "phone": phone,
            "network": network,
            "daily_food": daily_food,
            "daily_other": daily_other,
            "total_funds": total_funds,
            "duration_weeks": duration_weeks,
            "mode": mode,
            "locked": profile["locked"],
        }
        st.toast("Plan saved", icon=":material/check_circle:")

elif page == "Admin desk" and st.session_state.admin_authenticated:
    st.title("Admin desk", icon=":material/verified_user:")
    st.write("Review the next payout batch, reconcile the vault ledger, and release approved drops.")

    k1, k2, k3 = st.columns(3)
    k1.metric("Students covered", "128", "+14 this week", border=True)
    k2.metric("Next payout batch", money(1840000), "24 students", border=True)
    k3.metric("Ledger match", "99.8%", "Reconciled today", border=True)

    st.subheader("Monday payout queue", divider="gray")
    rows = [
        {"Student": "Amara K.", "Network": "MTN", "Phone": "0782 456 890", "Amount": money(plan["safe_weekly_drop"]), "Status": "Ready"},
        {"Student": "Joel M.", "Network": "Airtel", "Phone": "0701 883 214", "Amount": "UGX 175,000", "Status": "Ready"},
        {"Student": "Nabirye S.", "Network": "MTN", "Phone": "0774 102 665", "Amount": "UGX 210,000", "Status": "Needs review"},
        {"Student": "David O.", "Network": "Airtel", "Phone": "0755 430 118", "Amount": "UGX 160,000", "Status": "Ready"},
    ]
    st.dataframe(rows, width="stretch", hide_index=True, column_config={"Status": st.column_config.TextColumn("Status")})
    st.caption(f"Next scheduled release: Monday, {next_monday().strftime('%d %B %Y')} at 07:00 EAT")
    if not st.session_state.approved:
        if st.button("Approve ready payouts", type="primary", icon=":material/send:"):
            st.session_state.approved = True
            st.toast("Payout batch approved for dispatch", icon=":material/check_circle:")
    else:
        st.success("Ready payouts approved. Dispatch is simulated in this prototype.", icon=":material/check_circle:")

else:
    st.title(f"Good morning, {profile['name'].split()[0]}", icon=":material/waving_hand:")
    st.write("Your essentials are paced. You can make today’s choices with a little more room to breathe.")

    with st.container(horizontal=True):
        st.metric("Vault balance", money(profile["total_funds"]), "Locked principal", border=True)
        st.metric("Weekly drop", money(plan["safe_weekly_drop"]), "Every Monday · 07:00", border=True)
        st.metric("Daily target", money(plan["daily_baseline"]), "Food + essentials", border=True)

    st.space("small")
    left, right = st.columns([1.35, 1])
    with left:
        with st.container(border=True):
            st.subheader("Meal guarantee status", icon=":material/shield:")
            st.badge("Secured", icon=":material/check_circle:", color="green")
            st.markdown(f"### Covered through {(date.today() + timedelta(days=int(plan['coverage_days']))).strftime('%d %b %Y')}")
            st.progress(min(plan["coverage_days"] / (profile["duration_weeks"] * 7), 1.0))
            st.caption(f"{plan['coverage_days']:.0f} days of baseline cover · locked in your vault")

        with st.container(border=True):
            st.subheader("Your next drop", icon=":material/event:")
            drop_date = next_monday()
            st.markdown(f"### {drop_date.strftime('%A, %d %B')}")
            st.write(f"**{money(plan['safe_weekly_drop'])}** to {profile['network']} · {profile['phone']}")
            st.caption("Scheduled automatically. You will receive an SMS when it is dispatched.")

    with right:
        with st.container(border=True):
            st.subheader("Expense baseline", icon=":material/tune:")
            st.metric("Food", money(profile["daily_food"]))
            st.metric("Transport + airtime", money(profile["daily_other"]))
            st.caption("This is your recommended daily ceiling between drops.")

        with st.container(border=True):
            st.subheader("Recent activity", icon=":material/history:")
            st.markdown(f"**{money(plan['safe_weekly_drop'])}** · Monday drop")
            st.caption("Processed 2 days ago")
            st.markdown(f"**{money(profile['total_funds'])}** · Vault deposit")
            st.caption("Locked 14 days ago")
