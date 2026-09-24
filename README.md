# CampusFlow MVP

A Streamlit prototype for automated student allowance pacing and a financial lockbox workflow.

## Run locally

```bash
source .venv/Scripts/activate
streamlit run app.py
```

Open http://localhost:8501.

## Publish with Streamlit Community Cloud

1. Commit and push the project to the `main` branch on GitHub.
2. Open [share.streamlit.io](https://share.streamlit.io) and sign in with GitHub.
3. Select `EugeneNathanOguli/campusflow-mvp`, branch `main`, and file `app.py`.
4. In the app settings, add the contents of `.streamlit/secrets.toml` under **Secrets**. Never upload `secrets.toml` to GitHub.
5. Deploy the app and test the complete five-step student flow using the generated URL.

For the first public demo, use a strong `admin_passcode` in the Cloud secrets. Keep authentication disabled until the OIDC provider is configured; the app will remain in demo mode with simulated balances and payouts.

### Configure Supabase persistence

Create a Supabase project, open its SQL editor, and run:

```sql
create table public.workspaces (
	user_key text primary key,
	profile jsonb not null,
	workflow jsonb not null,
	created_at timestamptz not null default now(),
	updated_at timestamptz not null default now()
);
```

Add the project URL and **service-role key** to Streamlit secrets under `[supabase]`. The service-role key must stay server-side and must never be placed in frontend code or committed to Git. Supabase persistence is used only after OIDC authentication is enabled; otherwise demo sessions remain non-persistent.

## Local admin access

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`, then replace the example value with a long random passcode. The secrets file is ignored by Git and must never be committed.

The Admin desk is intentionally hidden unless OIDC authentication is enabled and an admin passcode is configured. The shared passcode is suitable only for this MVP; production admin access should use identity-based roles and an audit trail.

## Authentication and privacy

Local development runs in demo mode with sample data. For a deployed app, configure the `[auth]` OIDC values in `secrets.toml` using Google, Microsoft Entra, Auth0, or another OpenID Connect provider. Once `client_id` is present, CampusFlow requires sign-in before rendering the workspace and provides a sign-out control.

Authentication alone is not enough for real financial data. A production release also needs:

- A database with one student profile per authenticated account.
- Server-side authorization on every profile, vault, and payout query.
- HTTPS, encrypted backups, audit logs, rate limiting, and monitoring.
- Secure payment-provider webhooks and an immutable payout ledger.
- A formal privacy policy, retention rules, and appropriate regulatory review.

This prototype uses simulated balances and payout approvals. It does not connect to Mobile Money, XENO, a bank, or a production database.

Authenticated MVP workspaces are stored in a local SQLite file named `campusflow.db`, keyed by the identity-provider user ID. That file is ignored by Git. Unauthenticated demo sessions do not read or write the database, preventing different visitors from sharing one profile. Local authenticated development can restore a user's profile and progress after they sign in again, but Streamlit Community Cloud storage is not a durable production database. Before handling real financial data, replace SQLite with a hosted database such as PostgreSQL or Supabase and add server-side authorization for every query.

## Save to GitHub with Git Bash

Run these commands from the project folder in the VS Code Git Bash terminal:

```bash
git init
git add .
git status
git commit -m "Create CampusFlow MVP"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/campusflow-mvp.git
git push -u origin main
```

Keep the GitHub repository private. The local `.streamlit/secrets.toml` file is excluded from Git; only commit `.streamlit/secrets.toml.example`.
